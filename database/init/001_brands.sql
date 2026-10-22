CREATE TABLE public.brands
(
    brand_id integer GENERATED ALWAYS AS IDENTITY,
    brand_name character varying(100) NOT NULL,
    CONSTRAINT brands_pkey PRIMARY KEY (brand_id)
);