-- Table: public.mobile_images

-- DROP TABLE IF EXISTS public.mobile_images;

CREATE TABLE IF NOT EXISTS public.mobile_images
(
    image_id serial NOT NULL,
    variant_id integer NOT NULL,
    image_url character varying(255) COLLATE pg_catalog."default" NOT NULL,
    image_type character varying(50) COLLATE pg_catalog."default",
    uploaded_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT mobile_images_pkey PRIMARY KEY (image_id),
    CONSTRAINT fk_image_variant FOREIGN KEY (variant_id)
        REFERENCES public.phone_variants (variant_id) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE CASCADE
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS public.mobile_images
    OWNER to postgres;
