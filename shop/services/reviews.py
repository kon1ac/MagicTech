"""Отзывы и вопросы: проверка покупки, премодерация, атомарный пересчёт рейтинга."""

from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Avg, Count
from django.utils import timezone

from shop.models import Order, Product, Review
from shop.services.audit import write_audit


def purchased_order(user, product: Product) -> Order | None:
    """Проверка «покупал ли» — по завершённому заказу с этим товаром."""
    if user is None:
        return None
    return (
        Order.objects.filter(id_user=user, order_status__in=['COMPLETED', 'RETURNED'], items__id_product=product)
        .order_by('-created_at')
        .first()
    )


@transaction.atomic
def create_review(user, product: Product, *, rating: int | None, text: str, photo=None,
                  is_question: bool = False, request=None) -> Review:
    text = (text or '').strip()
    if not text:
        raise ValidationError('Текст не может быть пустым.')
    if len(text) > 5000:
        raise ValidationError('Слишком длинный текст.')
    order = None
    if not is_question:
        order = purchased_order(user, product)
        if order is None:
            raise ValidationError('Оставить отзыв может только покупатель, получивший этот товар.')
        if Review.objects.filter(id_user=user, id_product=product, review_type='review').exists():
            raise ValidationError('Вы уже оставили отзыв на этот товар.')
        if rating is None or not 1 <= int(rating) <= 5:
            raise ValidationError('Оценка — от 1 до 5.')
    review = Review.objects.create(
        id_product=product, id_user=user, id_order=order,
        review_type='question' if is_question else 'review',
        review_rating=None if is_question else int(rating),
        review_text=text, review_photo=photo, review_status='pending',
    )
    write_audit(user=user, object_type='review', object_id=review.id_review, action='create',
                after={'product': product.product_sku, 'rating': review.review_rating}, request=request)
    return review


def recalc_rating(product_id: int) -> None:
    """Атомарный пересчёт среднего рейтинга (строка товара блокируется)."""
    product = Product.objects.select_for_update().get(pk=product_id)
    agg = Review.objects.filter(
        id_product_id=product_id, review_type='review', review_status='approved'
    ).aggregate(avg=Avg('review_rating'), cnt=Count('id_review'))
    product.rating_avg = Decimal(agg['avg'] or 0).quantize(Decimal('0.01'))
    product.rating_count = agg['cnt']
    product.save(update_fields=['rating_avg', 'rating_count'])


@transaction.atomic
def moderate(review: Review, status: str, *, actor, request=None) -> Review:
    if status not in {'pending', 'approved', 'rejected'}:
        raise ValidationError('Неизвестный статус.')
    review = Review.objects.select_for_update().get(pk=review.pk)
    before = {'status': review.review_status}
    review.review_status = status
    review.save(update_fields=['review_status', 'updated_at'])
    recalc_rating(review.id_product_id)
    write_audit(user=actor, object_type='review', object_id=review.id_review, action='moderate',
                before=before, after={'status': status}, request=request)
    return review


@transaction.atomic
def answer(review: Review, text: str, *, actor, request=None) -> Review:
    text = (text or '').strip()
    if not text:
        raise ValidationError('Ответ не может быть пустым.')
    before = {'seller_answer': review.seller_answer}
    review.seller_answer = text
    review.answered_at = timezone.now()
    review.save(update_fields=['seller_answer', 'answered_at', 'updated_at'])
    write_audit(user=actor, object_type='review', object_id=review.id_review, action='answer',
                before=before, after={'seller_answer': text}, request=request)
    return review


@transaction.atomic
def delete_review(review: Review, *, actor, request=None) -> None:
    product_id, review_id = review.id_product_id, review.id_review
    review.delete()
    recalc_rating(product_id)
    write_audit(user=actor, object_type='review', object_id=review_id, action='delete', request=request)
