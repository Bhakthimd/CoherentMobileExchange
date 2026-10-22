CREATE TABLE IF NOT EXISTS public.phone_variants
(
    variant_id serial NOT NULL,
    model_id integer NOT NULL,
    storage_gb integer NOT NULL,
    ram_gb integer NOT NULL,
    color character varying(50),
    battery_capacity integer,
    listed_price numeric(10,2),
    rating numeric(3,2),
    stock_quantity integer DEFAULT 0,
    CONSTRAINT phone_variants_pkey PRIMARY KEY (variant_id),
    CONSTRAINT uq_model_variant UNIQUE (model_id, storage_gb, ram_gb, color),
    CONSTRAINT fk_variant_model FOREIGN KEY (model_id)
        REFERENCES public.phone_models (model_id)
        ON UPDATE NO ACTION
        ON DELETE CASCADE,
    CONSTRAINT chk_battery CHECK (battery_capacity > 0),
    CONSTRAINT chk_ram CHECK (ram_gb > 0),
    CONSTRAINT chk_rating CHECK (rating >= 0 AND rating <= 5),
    CONSTRAINT chk_stock CHECK (stock_quantity >= 0),
    CONSTRAINT chk_storage CHECK (storage_gb > 0)
);