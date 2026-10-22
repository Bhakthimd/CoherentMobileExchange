-- Table: public.pricing

-- DROP TABLE IF EXISTS public.pricing;

CREATE TABLE IF NOT EXISTS public.pricing
(
    pricing_id serial NOT NULL,
    variant_id integer NOT NULL,
    market_price numeric(10,2),
    original_price numeric(10,2),
    discount numeric(10,2) DEFAULT 0,
    current_price numeric(10,2) NOT NULL,
    price_date date NOT NULL DEFAULT CURRENT_DATE,
    CONSTRAINT pricing_pkey PRIMARY KEY (pricing_id),
    CONSTRAINT fk_pricing_variant FOREIGN KEY (variant_id)
        REFERENCES public.phone_variants (variant_id) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE CASCADE,
    CONSTRAINT chk_prices CHECK (market_price >= 0::numeric AND original_price >= 0::numeric AND discount >= 0::numeric AND current_price >= 0::numeric)
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS public.pricing
    OWNER to postgres;
