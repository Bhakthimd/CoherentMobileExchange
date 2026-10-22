CREATE TABLE IF NOT EXISTS public.phone_series
(
    series_id serial NOT NULL,
    brand_id integer NOT NULL,
    series_name character varying(100) NOT NULL,
    CONSTRAINT phone_series_pkey PRIMARY KEY (series_id),
    CONSTRAINT uq_brand_series UNIQUE (brand_id, series_name),
    CONSTRAINT fk_series_brand FOREIGN KEY (brand_id)
        REFERENCES public.brands (brand_id)
        ON UPDATE NO ACTION
        ON DELETE CASCADE
);