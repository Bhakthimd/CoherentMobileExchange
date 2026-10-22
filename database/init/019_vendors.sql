-- ============================================================================
-- CoherentMobiles Schema Additive Migration: Vendors & Vendor-Product Relation
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

-- Additive migration: Add foreign key vendor_id to phone_variants if present
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

-- Seed verified vendor partners
INSERT INTO public.vendors (vendor_name, vendor_code, category, contact_email, contact_phone, location, rating, status)
VALUES
('Coherent Retail Direct', 'CR-DIR', 'Direct Retail Partner', 'retail@coherentmobiles.com', '+91 98765 43210', 'Mumbai, Maharashtra', 4.9, 'Active'),
('Apex Mobile Distributors', 'APX-DST', 'Multi-Brand Authorized Wholesaler', 'contact@apexmobiles.in', '+91 98111 22334', 'Bengaluru, Karnataka', 4.8, 'Active'),
('iStore India Authorized', 'IST-IND', 'Premium Flagship Specialist', 'partner@istoreindia.com', '+91 98222 33445', 'New Delhi, NCR', 4.9, 'Active'),
('Nexus Gadgets Hub', 'NX-HUB', 'Regional Inventory Supplier', 'sales@nexusgadgets.in', '+91 98333 44556', 'Hyderabad, Telangana', 4.7, 'Active')
ON CONFLICT (vendor_code) DO NOTHING;
