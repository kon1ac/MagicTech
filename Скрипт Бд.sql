-- 1. Таблица: Учётные данные (авторизация)
CREATE TABLE auth_credentials (
    id_user        BIGSERIAL PRIMARY KEY,
    email          VARCHAR(255) NOT NULL UNIQUE,
    password_hash  VARCHAR(255) NOT NULL,
    user_role      VARCHAR(30)  NOT NULL,
    is_active      BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at     TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMP    NOT NULL DEFAULT NOW()
);

-- 2. Таблица: Профили пользователей (личные данные)
CREATE TABLE user_profiles (
    id_user              BIGINT PRIMARY KEY,
    profile_first_name   VARCHAR(100),
    profile_last_name    VARCHAR(100),
    profile_phone        VARCHAR(30),
    profile_address      TEXT,
    profile_avatar_url   VARCHAR(500),
    created_at           TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_user_profiles_auth
        FOREIGN KEY (id_user) REFERENCES auth_credentials(id_user)
        ON DELETE CASCADE ON UPDATE CASCADE
);

-- 3. Таблица: Категории
CREATE TABLE categories (
    id_category          BIGSERIAL PRIMARY KEY,
    id_parent            BIGINT,
    category_name        VARCHAR(255) NOT NULL,
    category_slug        VARCHAR(255) UNIQUE,
    category_level       SMALLINT     NOT NULL,
    category_attributes  JSONB,
    is_active            BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at           TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMP    NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_categories_parent
        FOREIGN KEY (id_parent) REFERENCES categories(id_category)
        ON DELETE SET NULL ON UPDATE CASCADE
);

-- 4. Таблица: Бренды/Производители
CREATE TABLE brands (
    id_brand            BIGSERIAL PRIMARY KEY,
    brand_name          VARCHAR(255) NOT NULL,
    brand_slug          VARCHAR(255) UNIQUE,
    brand_description   TEXT,
    brand_logo_url      VARCHAR(500),
    is_active           BOOLEAN      NOT NULL DEFAULT TRUE
);

-- 5. Таблица: Товары
CREATE TABLE products (
    id_product                BIGSERIAL PRIMARY KEY,
    product_sku               VARCHAR(100) NOT NULL UNIQUE,
    product_ean               VARCHAR(50)  UNIQUE,
    product_name              VARCHAR(255) NOT NULL,
    id_brand                  BIGINT,
    id_category               BIGINT,
    product_description       TEXT,
    product_characteristics   JSONB,
    product_images            JSONB,
    is_active                 BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at                TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at                TIMESTAMP    NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_products_brand
        FOREIGN KEY (id_brand) REFERENCES brands(id_brand)
        ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT fk_products_category
        FOREIGN KEY (id_category) REFERENCES categories(id_category)
        ON DELETE SET NULL ON UPDATE CASCADE
);

-- 6. Таблица: Цены (история цен)
CREATE TABLE prices (
    id_price        BIGSERIAL PRIMARY KEY,
    id_product      BIGINT NOT NULL,
    product_price   NUMERIC(12,2) NOT NULL,
    price_currency  VARCHAR(3)    NOT NULL DEFAULT 'RUB',
    valid_from      TIMESTAMP     NOT NULL DEFAULT NOW(),
    valid_to        TIMESTAMP,
    id_user         BIGINT,
    created_at      TIMESTAMP     NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_prices_product
        FOREIGN KEY (id_product) REFERENCES products(id_product)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_prices_user
        FOREIGN KEY (id_user) REFERENCES auth_credentials(id_user)
        ON DELETE SET NULL ON UPDATE CASCADE
);

-- 7. Таблица: Акции/Скидки/Промокоды
CREATE TABLE promotions (
    id_promotion           BIGSERIAL PRIMARY KEY,
    promotion_name         VARCHAR(255) NOT NULL,
    promotion_type         VARCHAR(20)  NOT NULL,
    promotion_value        NUMERIC(12,2) NOT NULL,
    start_at               TIMESTAMP    NOT NULL,
    end_at                 TIMESTAMP    NOT NULL,
    promotion_promo_code   VARCHAR(50),
    is_active              BOOLEAN      NOT NULL DEFAULT TRUE,
    id_user                BIGINT,
    created_at             TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMP    NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_promotions_user
        FOREIGN KEY (id_user) REFERENCES auth_credentials(id_user)
        ON DELETE SET NULL ON UPDATE CASCADE
);

-- 8. Таблица: Остатки и движения
CREATE TABLE stock (
    id_stock                  BIGSERIAL PRIMARY KEY,
    id_product                BIGINT NOT NULL,
    stock_quantity            INT    NOT NULL DEFAULT 0,
    stock_reserved            INT    NOT NULL DEFAULT 0,
    stock_movement_type       VARCHAR(20),
    stock_movement_history    JSONB,
    updated_at                TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_stock_product
        FOREIGN KEY (id_product) REFERENCES products(id_product)
        ON DELETE CASCADE ON UPDATE CASCADE
);

-- 9. Таблица: Корзины
CREATE TABLE carts (
    id_cart          BIGSERIAL PRIMARY KEY,
    id_user          BIGINT,
    cart_session_id  VARCHAR(100),
    cart_status      VARCHAR(20) NOT NULL DEFAULT 'active',
    created_at       TIMESTAMP   NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMP   NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_carts_user
        FOREIGN KEY (id_user) REFERENCES auth_credentials(id_user)
        ON DELETE SET NULL ON UPDATE CASCADE
);

-- 10. Таблица: Заказы
CREATE TABLE orders (
    id_order                BIGSERIAL PRIMARY KEY,
    order_number            VARCHAR(50) NOT NULL UNIQUE,
    id_user                 BIGINT NOT NULL,
    order_status            VARCHAR(20) NOT NULL DEFAULT 'NEW',
    total_items             NUMERIC(12,2) NOT NULL DEFAULT 0,
    discount_total          NUMERIC(12,2) NOT NULL DEFAULT 0,
    total                   NUMERIC(12,2) NOT NULL DEFAULT 0,
    order_payment_method    VARCHAR(30),
    order_payment_status    VARCHAR(20),
    created_at              TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_orders_user
        FOREIGN KEY (id_user) REFERENCES auth_credentials(id_user)
        ON DELETE RESTRICT ON UPDATE CASCADE
);

-- 11. Таблица: Платежи
CREATE TABLE payments (
    id_payment              BIGSERIAL PRIMARY KEY,
    id_order                BIGINT NOT NULL,
    payment_provider        VARCHAR(30) NOT NULL,
    payment_amount          NUMERIC(12,2) NOT NULL,
    payment_currency        VARCHAR(3) NOT NULL DEFAULT 'RUB',
    payment_status          VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    payment_refund_amount   NUMERIC(12,2),
    id_user                 BIGINT,
    created_at              TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_payments_order
        FOREIGN KEY (id_order) REFERENCES orders(id_order)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_payments_user
        FOREIGN KEY (id_user) REFERENCES auth_credentials(id_user)
        ON DELETE SET NULL ON UPDATE CASCADE
);

-- 12. Таблица: Возвраты и обмены
CREATE TABLE returns (
    id_return       BIGSERIAL PRIMARY KEY,
    id_order        BIGINT NOT NULL,
    id_user         BIGINT NOT NULL,
    return_reason   VARCHAR(255),
    return_status   VARCHAR(30) NOT NULL DEFAULT 'NEW',
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_returns_order
        FOREIGN KEY (id_order) REFERENCES orders(id_order)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_returns_user
        FOREIGN KEY (id_user) REFERENCES auth_credentials(id_user)
        ON DELETE RESTRICT ON UPDATE CASCADE
);

-- 13. Таблица: Отзывы и вопросы
CREATE TABLE reviews (
    id_review       BIGSERIAL PRIMARY KEY,
    id_product      BIGINT NOT NULL,
    id_user         BIGINT NOT NULL,
    id_order        BIGINT,
    review_type     VARCHAR(20) NOT NULL DEFAULT 'review',
    review_rating   SMALLINT,
    review_text     TEXT,
    review_status   VARCHAR(20) NOT NULL DEFAULT 'pending',
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_reviews_product
        FOREIGN KEY (id_product) REFERENCES products(id_product)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_reviews_user
        FOREIGN KEY (id_user) REFERENCES auth_credentials(id_user)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_reviews_order
        FOREIGN KEY (id_order) REFERENCES orders(id_order)
        ON DELETE SET NULL ON UPDATE CASCADE
);

-- 14. Таблица: Журнал изменений
CREATE TABLE audit_log (
    id_audit            BIGSERIAL PRIMARY KEY,
    id_user             BIGINT,
    audit_object_type   VARCHAR(50) NOT NULL,
    object_id           BIGINT,
    audit_action        VARCHAR(50) NOT NULL,
    created_at          TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_audit_log_user
        FOREIGN KEY (id_user) REFERENCES auth_credentials(id_user)
        ON DELETE SET NULL ON UPDATE CASCADE
);

-- Таблицы-связки (М:М)
-- 15. Таблица: Позиции заказа (Заказ ⇔ Товар)
CREATE TABLE order_items (
    id_order_item         BIGSERIAL PRIMARY KEY,
    id_order              BIGINT NOT NULL,
    id_product            BIGINT NOT NULL,
    order_item_quantity   INT NOT NULL,
    order_item_price      NUMERIC(12,2) NOT NULL,
    order_item_total      NUMERIC(12,2) NOT NULL,
    CONSTRAINT fk_order_items_order
        FOREIGN KEY (id_order) REFERENCES orders(id_order)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_order_items_product
        FOREIGN KEY (id_product) REFERENCES products(id_product)
        ON DELETE RESTRICT ON UPDATE CASCADE
);

-- 16. Таблица: Позиции корзины (Корзина ⇔ Товар)
CREATE TABLE cart_items (
    id_cart_item              BIGSERIAL PRIMARY KEY,
    id_cart                   BIGINT NOT NULL,
    id_product                BIGINT NOT NULL,
    cart_item_quantity        INT NOT NULL,
    cart_item_price_snapshot  NUMERIC(12,2) NOT NULL,
    CONSTRAINT fk_cart_items_cart
        FOREIGN KEY (id_cart) REFERENCES carts(id_cart)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_cart_items_product
        FOREIGN KEY (id_product) REFERENCES products(id_product)
        ON DELETE CASCADE ON UPDATE CASCADE
);

-- 17. Таблица: Товары в акции (Акция ⇔ Товар)
CREATE TABLE promotion_products (
    id_promotion_product  BIGSERIAL PRIMARY KEY,
    id_promotion          BIGINT NOT NULL,
    id_product            BIGINT NOT NULL,
    CONSTRAINT fk_promo_products_promotion
        FOREIGN KEY (id_promotion) REFERENCES promotions(id_promotion)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_promo_products_product
        FOREIGN KEY (id_product) REFERENCES products(id_product)
        ON DELETE CASCADE ON UPDATE CASCADE
);

-- 18. Таблица: Категории в акции (Акция ⇔ Категория)
CREATE TABLE promotion_categories (
    id_promotion_category  BIGSERIAL PRIMARY KEY,
    id_promotion           BIGINT NOT NULL,
    id_category            BIGINT NOT NULL,
    CONSTRAINT fk_promo_categories_promotion
        FOREIGN KEY (id_promotion) REFERENCES promotions(id_promotion)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_promo_categories_category
        FOREIGN KEY (id_category) REFERENCES categories(id_category)
        ON DELETE CASCADE ON UPDATE CASCADE
);

-- 19. Таблица: Бренды в акции (Акция ⇔ Бренд)
CREATE TABLE promotion_brands (
    id_promotion_brand  BIGSERIAL PRIMARY KEY,
    id_promotion        BIGINT NOT NULL,
    id_brand            BIGINT NOT NULL,
    CONSTRAINT fk_promo_brands_promotion
        FOREIGN KEY (id_promotion) REFERENCES promotions(id_promotion)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_promo_brands_brand
        FOREIGN KEY (id_brand) REFERENCES brands(id_brand)
        ON DELETE CASCADE ON UPDATE CASCADE
);

-- 20. Таблица: Применённые акции в заказе (Заказ ⇔ Акция)
CREATE TABLE order_promotions (
    id_order_promotion          BIGSERIAL PRIMARY KEY,
    id_order                    BIGINT NOT NULL,
    id_promotion                BIGINT NOT NULL,
    order_promotion_discount    NUMERIC(12,2) NOT NULL DEFAULT 0,
    CONSTRAINT fk_order_promotions_order
        FOREIGN KEY (id_order) REFERENCES orders(id_order)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_order_promotions_promotion
        FOREIGN KEY (id_promotion) REFERENCES promotions(id_promotion)
        ON DELETE CASCADE ON UPDATE CASCADE
);

-- 21. Таблица: Позиции возврата (Возврат ⇔ Позиция заказа)
CREATE TABLE return_items (
    id_return_item              BIGSERIAL PRIMARY KEY,
    id_return                   BIGINT NOT NULL,
    id_order_item               BIGINT NOT NULL,
    return_item_quantity        INT NOT NULL,
    return_item_refund_amount   NUMERIC(12,2) NOT NULL DEFAULT 0,
    CONSTRAINT fk_return_items_return
        FOREIGN KEY (id_return) REFERENCES returns(id_return)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_return_items_order_item
        FOREIGN KEY (id_order_item) REFERENCES order_items(id_order_item)
        ON DELETE RESTRICT ON UPDATE CASCADE
);


-- 1. auth_credentials (Учётные данные) — 5 разных ролей
INSERT INTO auth_credentials (id_user, email, password_hash, user_role, is_active, created_at, updated_at) VALUES
(1, 'admin_db@magictech.ru',   '$argon2id$v=19$m=65536,t=3,p=4$adminhash',   'admin_db',     TRUE, '2026-01-10 09:00:00', '2026-10-19 10:00:00'),
(2, 'merchandiser@magictech.ru','$argon2id$v=19$m=65536,t=3,p=4$merchhash',  'merchandiser', TRUE, '2026-01-12 10:00:00', '2026-10-19 10:05:00'),
(3, 'accountant@magictech.ru',  '$argon2id$v=19$m=65536,t=3,p=4$accounthash', 'accountant',   TRUE, '2026-01-15 09:00:00', '2026-10-19 10:10:00'),
(4, 'customer@mail.ru',         '$argon2id$v=19$m=65536,t=3,p=4$custhash',   'customer',     TRUE, '2026-02-15 11:30:00', '2026-10-19 10:15:00'),
(5, 'picker@magictech.ru',      '$argon2id$v=19$m=65536,t=3,p=4$pickerhash', 'picker',       TRUE, '2026-03-01 14:00:00', '2026-10-19 10:20:00');

-- 2. user_profiles (Профили) — ID соответствуют ролям
INSERT INTO user_profiles (id_user, profile_first_name, profile_last_name, profile_phone, profile_address, profile_avatar_url, created_at, updated_at) VALUES
(1, 'Илья', 'Егоров',  '+7 (977) 777-97-79', 'г. Москва, ул. Пушкина, д. 77, кв. 99', NULL, '2026-01-10 09:00:00', '2026-10-19 10:00:00'),
(2, 'Мария',   'Петрова',  '+7 (900) 333-44-55', 'г. Казань, ул. Баумана, д. 15, кв. 8', NULL, '2026-01-12 10:00:00', '2026-10-19 10:05:00'),
(3, 'Елена',   'Кузнецова','+7 (900) 555-66-77', 'г. Москва, ул. Тверская, д. 10, офис 5', NULL, '2026-01-15 09:00:00', '2026-10-19 10:10:00'),
(4, 'Иван',    'Иванов',   '+7 (900) 222-33-44', 'г. Санкт-Петербург, Невский пр., д. 20, кв. 5', NULL, '2026-02-15 11:30:00', '2026-10-19 10:15:00'),
(5, 'Сергей',  'Сидоров',  '+7 (900) 444-55-66', 'г. Новосибирск, ул. Ленина, д. 30, кв. 12', NULL, '2026-03-01 14:00:00', '2026-10-19 10:20:00');

-- 3. categories (Категории) — без изменений
INSERT INTO categories (id_category, id_parent, category_name, category_slug, category_level, category_attributes, is_active, created_at, updated_at) VALUES
(1, NULL, 'Клавиатуры',   'keyboards', 1, '{"types": ["механическая", "мембранная"], "connection": ["проводная", "беспроводная"]}', TRUE, '2026-01-01 09:00:00', '2026-10-19 09:00:00'),
(2, NULL, 'Мыши',         'mice',      1, '{"types": ["игровая", "офисная"], "connection": ["проводная", "беспроводная"]}', TRUE, '2026-01-01 09:05:00', '2026-10-19 09:00:00'),
(3, 1,    'Механические', 'mechanical-keyboards', 2, '{"switch": ["red", "blue", "brown"]}', TRUE, '2026-01-01 09:10:00', '2026-10-19 09:00:00'),
(4, 2,    'Игровые',      'gaming-mice', 2, '{"dpi": "до 16000"}', TRUE, '2026-01-01 09:15:00', '2026-10-19 09:00:00'),
(5, NULL, 'Наушники',     'headphones', 1, '{"types": ["накладные", "внутриканальные"], "connection": ["проводные", "беспроводные"]}', TRUE, '2026-01-01 09:20:00', '2026-10-19 09:00:00');

-- 4. brands (Бренды) — без изменений
INSERT INTO brands (id_brand, brand_name, brand_slug, brand_description, brand_logo_url, is_active) VALUES
(1, 'HyperX',    'hyperx',    'Игровые аксессуары и периферия', NULL, TRUE),
(2, 'Logitech',  'logitech',  'Периферия и аксессуары для ПК',  NULL, TRUE),
(3, 'Razer',     'razer',     'Игровое оборудование',           NULL, TRUE),
(4, 'A4Tech',    'a4tech',    'Бюджетная периферия',            NULL, TRUE),
(5, 'Sony',      'sony',      'Аудиотехника',                   NULL, TRUE);

-- 5. products (Товары) — без изменений
INSERT INTO products (id_product, product_sku, product_ean, product_name, id_brand, id_category, product_description, product_characteristics, product_images, is_active, created_at, updated_at) VALUES
(1, 'KB-HX-001', '4601111111111', 'Клавиатура HyperX Alloy FPS', 1, 3, 'Механическая игровая клавиатура с подсветкой', '{"switch": "red", "connection": "проводная", "backlight": "red"}', NULL, TRUE, '2026-01-10 10:00:00', '2026-10-19 10:00:00'),
(2, 'MS-LG-002', '4601111111112', 'Мышь Logitech G502 Hero', 2, 4, 'Игровая мышь с сенсором Hero 25K', '{"dpi": "25600", "connection": "проводная", "buttons": "11"}', NULL, TRUE, '2026-01-10 10:05:00', '2026-10-19 10:00:00'),
(3, 'HP-RZ-003', '4601111111113', 'Наушники Razer BlackShark V2', 3, 5, 'Игровые наушники с шумоподавлением', '{"connection": "проводные", "type": "накладные", "microphone": "да"}', NULL, TRUE, '2026-01-10 10:10:00', '2026-10-19 10:00:00'),
(4, 'MS-A4-004', '4601111111114', 'Мышь A4Tech Bloody V7', 4, 4, 'Игровая мышь с регулировкой DPI', '{"dpi": "3200", "connection": "проводная", "buttons": "7"}', NULL, TRUE, '2026-01-10 10:15:00', '2026-10-19 10:00:00'),
(5, 'HP-SN-005', '4601111111115', 'Наушники Sony WH-1000XM5', 5, 5, 'Беспроводные наушники с активным шумоподавлением', '{"connection": "беспроводные", "type": "накладные", "battery": "30ч"}', NULL, TRUE, '2026-01-10 10:20:00', '2026-10-19 10:00:00');

-- 6. prices (Цены) — id_user = 1 (Администратор БД)
INSERT INTO prices (id_price, id_product, product_price, price_currency, valid_from, valid_to, id_user, created_at) VALUES
(1, 1, 7990.00,  'RUB', '2026-01-10 10:00:00', NULL, 1, '2026-01-10 10:00:00'),
(2, 2, 5990.00,  'RUB', '2026-01-10 10:00:00', NULL, 1, '2026-01-10 10:00:00'),
(3, 3, 8990.00,  'RUB', '2026-01-10 10:00:00', NULL, 1, '2026-01-10 10:00:00'),
(4, 4, 2490.00,  'RUB', '2026-01-10 10:00:00', NULL, 1, '2026-01-10 10:00:00'),
(5, 5, 29990.00, 'RUB', '2026-01-10 10:00:00', NULL, 1, '2026-01-10 10:00:00');

-- 7. promotions (Акции) — id_user = 1 (Администратор БД)
INSERT INTO promotions (id_promotion, promotion_name, promotion_type, promotion_value, start_at, end_at, promotion_promo_code, is_active, id_user, created_at, updated_at) VALUES
(1, 'Осенняя распродажа', 'percent', 10.00, '2026-10-01 00:00:00', '2026-10-31 23:59:59', 'AUTUMN2026', TRUE, 1, '2026-09-25 10:00:00', '2026-10-19 10:00:00'),
(2, 'Скидка на игровые мыши', 'fixed', 500.00, '2026-10-10 00:00:00', '2026-10-25 23:59:59', 'MOUSE500', TRUE, 1, '2026-10-05 10:00:00', '2026-10-19 10:00:00'),
(3, 'Чёрная пятница (ранняя)', 'percent', 15.00, '2026-11-01 00:00:00', '2026-11-30 23:59:59', 'BLACK2026', FALSE, 1, '2026-10-15 10:00:00', '2026-10-19 10:00:00'),
(4, 'Скидка на наушники Sony', 'fixed', 2000.00, '2026-10-15 00:00:00', '2026-10-31 23:59:59', 'SONY2000', TRUE, 1, '2026-10-10 10:00:00', '2026-10-19 10:00:00'),
(5, 'Первый заказ', 'percent', 5.00, '2026-01-01 00:00:00', '2026-12-31 23:59:59', 'WELCOME5', TRUE, 1, '2026-01-01 10:00:00', '2026-10-19 10:00:00');

-- 8. stock (Остатки) — без изменений
INSERT INTO stock (id_stock, id_product, stock_quantity, stock_reserved, stock_movement_type, stock_movement_history, updated_at) VALUES
(1, 1, 25,  2, 'income',    '[{"date": "2026-10-01", "qty": 30, "type": "income"}]', '2026-10-19 10:00:00'),
(2, 2, 40,  5, 'income',    '[{"date": "2026-10-01", "qty": 50, "type": "income"}]', '2026-10-19 10:00:00'),
(3, 3, 15,  1, 'income',    '[{"date": "2026-10-05", "qty": 20, "type": "income"}]', '2026-10-19 10:00:00'),
(4, 4, 60, 10, 'income',    '[{"date": "2026-10-10", "qty": 70, "type": "income"}]', '2026-10-19 10:00:00'),
(5, 5,  8,  1, 'income',    '[{"date": "2026-10-15", "qty": 10, "type": "income"}]', '2026-10-19 10:00:00');

-- 9. carts (Корзины) — все id_user = 4 (Покупатель) или NULL (гость)
INSERT INTO carts (id_cart, id_user, cart_session_id, cart_status, created_at, updated_at) VALUES
(1, 4, 'sess_customer_001', 'active',    '2026-10-19 09:00:00', '2026-10-19 09:30:00'),
(2, 4, 'sess_customer_002', 'active',    '2026-10-19 09:10:00', '2026-10-19 09:40:00'),
(3, 4, 'sess_customer_003', 'converted', '2026-10-18 15:00:00', '2026-10-18 15:20:00'),
(4, NULL, 'guest_abc123',   'active',    '2026-10-19 08:00:00', '2026-10-19 08:15:00'),
(5, 4, 'sess_customer_004', 'saved',     '2026-10-15 12:00:00', '2026-10-15 12:30:00');

-- 10. orders (Заказы) — все id_user = 4 (Покупатель)
INSERT INTO orders (id_order, order_number, id_user, order_status, total_items, discount_total, total, order_payment_method, order_payment_status, created_at, updated_at) VALUES
(1, 'MT-2026-0001', 4, 'COMPLETED', 13980.00, 0.00,    13980.00, 'online_yookassa', 'SUCCESS',  '2026-10-01 10:00:00', '2026-10-05 12:00:00'),
(2, 'MT-2026-0002', 4, 'PAID',      8990.00,  899.00,  8091.00,  'online_yookassa', 'SUCCESS',  '2026-10-10 14:00:00', '2026-10-10 14:05:00'),
(3, 'MT-2026-0003', 4, 'ASSEMBLY',  2490.00,  500.00,  1990.00,  'online_yookassa', 'SUCCESS',  '2026-10-18 16:00:00', '2026-10-19 09:00:00'),
(4, 'MT-2026-0004', 4, 'NEW',       29990.00, 0.00,    29990.00, 'on_receipt',      'PENDING',  '2026-10-19 09:00:00', '2026-10-19 09:00:00'),
(5, 'MT-2026-0005', 4, 'CANCELLED', 5990.00,  0.00,    5990.00,  'online_yookassa', 'REFUNDED', '2026-10-12 11:00:00', '2026-10-13 10:00:00');

-- 11. payments (Платежи) — id_user = 4 (кто платил) или 3 (бухгалтер)
INSERT INTO payments (id_payment, id_order, payment_provider, payment_amount, payment_currency, payment_status, payment_refund_amount, id_user, created_at, updated_at) VALUES
(1, 1, 'yookassa', 13980.00, 'RUB', 'SUCCESS',  NULL,    4, '2026-10-01 10:05:00', '2026-10-01 10:06:00'),
(2, 2, 'yookassa', 8091.00,  'RUB', 'SUCCESS',  NULL,    4, '2026-10-10 14:02:00', '2026-10-10 14:03:00'),
(3, 3, 'yookassa', 1990.00,  'RUB', 'SUCCESS',  NULL,    4, '2026-10-18 16:05:00', '2026-10-18 16:06:00'),
(4, 5, 'yookassa', 5990.00,  'RUB', 'REFUNDED', 5990.00, 3, '2026-10-12 11:05:00', '2026-10-13 10:00:00'),
(5, 4, 'manual',   29990.00, 'RUB', 'PENDING',  NULL,    NULL, '2026-10-19 09:05:00', '2026-10-19 09:05:00');

-- 12. returns (Возвраты) — все id_user = 4 (Покупатель)
INSERT INTO returns (id_return, id_order, id_user, return_reason, return_status, created_at, updated_at) VALUES
(1, 5, 4, 'Брак товара', 'REFUNDED', '2026-10-12 12:00:00', '2026-10-13 10:00:00'),
(2, 1, 4, 'Не подошёл товар', 'APPROVED', '2026-10-15 10:00:00', '2026-10-16 10:00:00'),
(3, 2, 4, 'Повреждение при транспортировке', 'IN_REVIEW', '2026-10-19 08:00:00', '2026-10-19 08:00:00'),
(4, 3, 4, 'Передумал', 'NEW', '2026-10-19 11:00:00', '2026-10-19 11:00:00'),
(5, 1, 4, 'Ошибка в заказе', 'REJECTED', '2026-10-17 15:00:00', '2026-10-18 09:00:00');

-- 13. reviews (Отзывы) — id_user = 4 (Покупатель)
INSERT INTO reviews (id_review, id_product, id_user, id_order, review_type, review_rating, review_text, review_status, created_at, updated_at) VALUES
(1, 1, 4, 1, 'review',   5, 'Отличная клавиатура, приятно печатать!', 'published', '2026-10-06 10:00:00', '2026-10-06 10:00:00'),
(2, 3, 4, 2, 'review',   4, 'Хорошие наушники, но микрофон мог бы быть лучше.', 'published', '2026-10-11 12:00:00', '2026-10-11 12:00:00'),
(3, 4, 4, 3, 'review',   3, 'Нормально за свои деньги, но софт сыроват.', 'pending', '2026-10-19 09:30:00', '2026-10-19 09:30:00'),
(4, 5, 4, 4, 'question', NULL, 'А есть ли у этих наушников чехол в комплекте?', 'published', '2026-10-19 09:10:00', '2026-10-19 09:10:00'),
(5, 2, 4, 5, 'review',   2, 'Мышь проработала две недели и начала двойной клик.', 'rejected', '2026-10-13 10:30:00', '2026-10-14 09:00:00');

-- 14. audit_log (Журнал изменений) — id_user = 1 (Администратор БД) или 3 (Бухгалтер)
INSERT INTO audit_log (id_audit, id_user, audit_object_type, object_id, audit_action, created_at) VALUES
(1, 1, 'products',  1, 'CREATE', '2026-01-10 10:00:00'),
(2, 1, 'products',  2, 'UPDATE', '2026-10-19 10:00:00'),
(3, 3, 'payments',  4, 'REFUND', '2026-10-13 10:00:00'),
(4, 1, 'promotions',3, 'CREATE', '2026-10-15 10:00:00'),
(5, 1, 'orders',    3, 'STATUS_CHANGE', '2026-10-19 09:00:00');

-- 15. order_items (Позиции заказов) — без изменений
INSERT INTO order_items (id_order_item, id_order, id_product, order_item_quantity, order_item_price, order_item_total) VALUES
(1, 1, 1, 1, 7990.00,  7990.00),
(2, 1, 2, 1, 5990.00,  5990.00),
(3, 2, 3, 1, 8990.00,  8990.00),
(4, 3, 4, 1, 2490.00,  2490.00),
(5, 4, 5, 1, 29990.00, 29990.00);

-- 16. cart_items (Позиции корзин) — без изменений
INSERT INTO cart_items (id_cart_item, id_cart, id_product, cart_item_quantity, cart_item_price_snapshot) VALUES
(1, 1, 1, 1, 7990.00),
(2, 1, 2, 1, 5990.00),
(3, 2, 3, 1, 8990.00),
(4, 3, 4, 1, 2490.00),
(5, 4, 5, 1, 29990.00);

-- 17. promotion_products (Товары в акции) — без изменений
INSERT INTO promotion_products (id_promotion_product, id_promotion, id_product) VALUES
(1, 1, 1),
(2, 1, 2),
(3, 2, 4),
(4, 4, 5),
(5, 3, 3);

-- 18. promotion_categories (Категории в акции) — без изменений
INSERT INTO promotion_categories (id_promotion_category, id_promotion, id_category) VALUES
(1, 1, 1),
(2, 1, 2),
(3, 2, 4),
(4, 3, 5),
(5, 5, 1);

-- 19. promotion_brands (Бренды в акции) — без изменений
INSERT INTO promotion_brands (id_promotion_brand, id_promotion, id_brand) VALUES
(1, 1, 1),
(2, 1, 2),
(3, 2, 3),
(4, 4, 5),
(5, 3, 2);

-- 20. order_promotions (Применённые акции в заказах) — без изменений
INSERT INTO order_promotions (id_order_promotion, id_order, id_promotion, order_promotion_discount) VALUES
(1, 1, 5, 699.00),
(2, 2, 1, 899.00),
(3, 3, 2, 500.00),
(4, 4, 4, 2000.00),
(5, 5, 5, 299.50);

-- 21. return_items (Позиции возврата) — без изменений
INSERT INTO return_items (id_return_item, id_return, id_order_item, return_item_quantity, return_item_refund_amount) VALUES
(1, 1, 5, 1, 5990.00),
(2, 2, 1, 1, 7990.00),
(3, 3, 3, 1, 8990.00),
(4, 4, 4, 1, 2490.00),
(5, 5, 2, 1, 5990.00);
