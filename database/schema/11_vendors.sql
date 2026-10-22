-- ============================================================================
-- CoherentMobiles Schema: Vendors & Vendor-Product Relation
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.vendors (
    vendor_id integer GENERATED ALWAYS AS IDENTITY,
    vendor_name character varying(150) NOT NULL,
    vendor_code character varying(50) NOT NULL UNIQUE,
    category character varying(100),
    contact_email character varying(100),
    contact_phone character varying(30),
    location character varying(150),
    rating numeric(3,2) DEFAULT 4.8,
    status character varying(30) DEFAULT 'Active',
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT vendors_pkey PRIMARY KEY (vendor_id)
);

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables 
        WHERE table_schema = 'public' AND table_name = 'phone_variants'
    ) THEN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_schema = 'public' AND table_name = 'phone_variants' AND column_name = 'vendor_id'
        ) THEN
            ALTER TABLE public.phone_variants 
            ADD COLUMN vendor_id integer REFERENCES public.vendors(vendor_id) ON DELETE SET NULL;
        END IF;
    END IF;
END $$;
