-- Migration: Directory Category Management (all 4 Directory modules)
-- Creates the two reference tables that back the category/subcategory
-- picker used by Community Map, Business Directory, Organization Directory,
-- and Emergency Directory, then seeds the starter taxonomy for all 4
-- modules. This is the final consolidated shape (module-scoped from the
-- start) — mirrors what BBCB Site ended up with after its own incremental
-- migrations.
-- Run this in the Supabase SQL Editor before deploying the Directory
-- Management backend.

CREATE TABLE IF NOT EXISTS directory_category_groups (
    id            TEXT         PRIMARY KEY,
    module        TEXT         NOT NULL DEFAULT 'business',
    name          TEXT         NOT NULL,
    icon          TEXT         NOT NULL DEFAULT '',
    color         TEXT         NOT NULL DEFAULT 'blue',
    display_order INTEGER      NOT NULL DEFAULT 0,
    active        BOOLEAN      NOT NULL DEFAULT true,
    created_at    TIMESTAMPTZ           DEFAULT now(),
    updated_at    TIMESTAMPTZ           DEFAULT now(),
    UNIQUE (module, name)
);

CREATE TABLE IF NOT EXISTS directory_subcategories (
    id            TEXT         PRIMARY KEY,
    module        TEXT         NOT NULL DEFAULT 'business',
    group_id      TEXT         NOT NULL REFERENCES directory_category_groups(id) ON DELETE CASCADE,
    name          TEXT         NOT NULL,
    description   TEXT         NOT NULL DEFAULT '',
    display_order INTEGER      NOT NULL DEFAULT 0,
    active        BOOLEAN      NOT NULL DEFAULT true,
    created_at    TIMESTAMPTZ           DEFAULT now(),
    updated_at    TIMESTAMPTZ           DEFAULT now(),
    UNIQUE (module, name)
);

-- ── Seed: Business Directory (module = 'business') — 12 groups ────────────
INSERT INTO directory_category_groups (id, module, name, icon, color, display_order) VALUES
    ('restaurant',        'business', 'Restaurant',             '🍽', 'blue', 1),
    ('cafes-bakeries',    'business', 'Cafes & Bakeries',       '☕', 'teal', 2),
    ('shopping-retail',   'business', 'Shopping & Retail',      '🛍', 'gold', 3),
    ('healthcare',        'business', 'Healthcare',             '🏥', 'red',  4),
    ('education',         'business', 'Education',              '🎓', 'blue', 5),
    ('services',          'business', 'Services',               '🛠', 'teal', 6),
    ('government',        'business', 'Government',             '🏛', 'gold', 7),
    ('parks-recreation',  'business', 'Parks & Recreation',     '🌳', 'red',  8),
    ('salons-beauty',     'business', 'Salons & Beauty',        '💇', 'blue', 9),
    ('hotels-accom',      'business', 'Hotels & Accommodations','🏨', 'teal', 10),
    ('transportation',    'business', 'Transportation',         '🚍', 'gold', 11),
    ('finance-banking',   'business', 'Finance & Banking',      '💳', 'red',  12)
ON CONFLICT (id) DO NOTHING;

INSERT INTO directory_subcategories (id, module, group_id, name, display_order) VALUES
    -- Restaurant
    ('restaurants',        'business', 'restaurant', 'Restaurants',         1),
    ('fast-food',          'business', 'restaurant', 'Fast Food',           2),
    ('eateries',           'business', 'restaurant', 'Eateries',            3),
    ('food-stalls',        'business', 'restaurant', 'Food Stalls',         4),
    ('carinderia',         'business', 'restaurant', 'Carinderia',          5),
    ('grill-house',        'business', 'restaurant', 'Grill House',         6),
    ('seafood-restaurant', 'business', 'restaurant', 'Seafood Restaurant',  7),

    -- Cafes & Bakeries
    ('coffee-shops',   'business', 'cafes-bakeries', 'Coffee Shops',    1),
    ('cafes',          'business', 'cafes-bakeries', 'Cafes',           2),
    ('milk-tea-shops', 'business', 'cafes-bakeries', 'Milk Tea Shops',  3),
    ('bakeries',       'business', 'cafes-bakeries', 'Bakeries',        4),
    ('pastry-shops',   'business', 'cafes-bakeries', 'Pastry Shops',    5),
    ('dessert-shops',  'business', 'cafes-bakeries', 'Dessert Shops',   6),

    -- Shopping & Retail
    ('grocery-stores',        'business', 'shopping-retail', 'Grocery Stores',          1),
    ('convenience-stores',    'business', 'shopping-retail', 'Convenience Stores',      2),
    ('supermarkets',          'business', 'shopping-retail', 'Supermarkets',            3),
    ('hardware-stores',       'business', 'shopping-retail', 'Hardware Stores',         4),
    ('agricultural-supply',   'business', 'shopping-retail', 'Agricultural Supply',     5),
    ('clothing-stores',       'business', 'shopping-retail', 'Clothing Stores',         6),
    ('electronics',           'business', 'shopping-retail', 'Electronics',             7),
    ('furniture',             'business', 'shopping-retail', 'Furniture',               8),
    ('gift-shops',            'business', 'shopping-retail', 'Gift Shops',              9),
    ('pharmacies-retail',     'business', 'shopping-retail', 'Pharmacies (Retail)',     10),
    ('water-refilling',       'business', 'shopping-retail', 'Water Refilling Stations',11),
    ('pet-supply-stores',     'business', 'shopping-retail', 'Pet Supply Stores',       12),
    ('bookstores',            'business', 'shopping-retail', 'Bookstores',              13),
    ('general-store',         'business', 'shopping-retail', 'General Store',           14),

    -- Healthcare
    ('hospital',             'business', 'healthcare', 'Hospital',             1),
    ('medical-clinic',       'business', 'healthcare', 'Medical Clinic',       2),
    ('dental-clinic',        'business', 'healthcare', 'Dental Clinic',        3),
    ('health-center',        'business', 'healthcare', 'Health Center',        4),
    ('pharmacy',             'business', 'healthcare', 'Pharmacy',             5),
    ('diagnostic-laboratory','business', 'healthcare', 'Diagnostic Laboratory',6),
    ('veterinary-clinic',    'business', 'healthcare', 'Veterinary Clinic',    7),
    ('animal-hospital',      'business', 'healthcare', 'Animal Hospital',      8),
    ('birthing-center',      'business', 'healthcare', 'Birthing Center',      9),

    -- Education
    ('elementary-school',  'business', 'education', 'Elementary School',  1),
    ('high-school',        'business', 'education', 'High School',        2),
    ('senior-high-school', 'business', 'education', 'Senior High School', 3),
    ('college',            'business', 'education', 'College',            4),
    ('university',         'business', 'education', 'University',         5),
    ('daycare-center',     'business', 'education', 'Daycare Center',      6),
    ('training-center',    'business', 'education', 'Training Center',     7),
    ('tutorial-center',    'business', 'education', 'Tutorial Center',     8),
    ('tesda-center',       'business', 'education', 'TESDA Center',        9),

    -- Services
    ('computer-repair',      'business', 'services', 'Computer Repair',       1),
    ('mobile-phone-repair',  'business', 'services', 'Mobile Phone Repair',   2),
    ('laundry-service',      'business', 'services', 'Laundry Service',       3),
    ('tailoring',            'business', 'services', 'Tailoring',             4),
    ('printing-services',    'business', 'services', 'Printing Services',     5),
    ('photography-studio',   'business', 'services', 'Photography Studio',    6),
    ('internet-cafe',        'business', 'services', 'Internet Café',         7),
    ('auto-repair',          'business', 'services', 'Auto Repair',           8),
    ('vulcanizing-shop',     'business', 'services', 'Vulcanizing Shop',      9),
    ('car-wash',             'business', 'services', 'Car Wash',              10),
    ('appliance-repair',     'business', 'services', 'Appliance Repair',      11),
    ('welding-shop',         'business', 'services', 'Welding Shop',          12),
    ('construction-services','business', 'services', 'Construction Services',13),
    ('event-services',       'business', 'services', 'Event Services',        14),
    ('funeral-services',     'business', 'services', 'Funeral Services',      15),
    ('cleaning-services',    'business', 'services', 'Cleaning Services',     16),
    ('general-services',     'business', 'services', 'General Services',      17),

    -- Government
    ('barangay-hall-cat',      'business', 'government', 'Barangay Hall',           1),
    ('municipal-offices',      'business', 'government', 'Municipal Offices',       2),
    ('police-station',         'business', 'government', 'Police Station',         3),
    ('fire-station',           'business', 'government', 'Fire Station',           4),
    ('post-office',            'business', 'government', 'Post Office',            5),
    ('government-agencies',    'business', 'government', 'Government Agencies',    6),
    ('public-service-offices', 'business', 'government', 'Public Service Offices', 7),

    -- Parks & Recreation
    ('public-parks',            'business', 'parks-recreation', 'Public Parks',             1),
    ('basketball-courts',       'business', 'parks-recreation', 'Basketball Courts',        2),
    ('sports-complex',          'business', 'parks-recreation', 'Sports Complex',           3),
    ('playgrounds',             'business', 'parks-recreation', 'Playgrounds',              4),
    ('open-spaces',             'business', 'parks-recreation', 'Open Spaces',              5),
    ('recreational-facilities', 'business', 'parks-recreation', 'Recreational Facilities',  6),
    ('community-centers',       'business', 'parks-recreation', 'Community Centers',        7),

    -- Salons & Beauty
    ('beauty-salon',    'business', 'salons-beauty', 'Beauty Salon',    1),
    ('hair-salon',      'business', 'salons-beauty', 'Hair Salon',      2),
    ('spa',             'business', 'salons-beauty', 'Spa',             3),
    ('massage',         'business', 'salons-beauty', 'Massage',         4),
    ('nail-salon',      'business', 'salons-beauty', 'Nail Salon',      5),
    ('barbershop',      'business', 'salons-beauty', 'Barbershop',      6),
    ('skin-care-clinic','business', 'salons-beauty', 'Skin Care Clinic',7),
    ('wellness-center', 'business', 'salons-beauty', 'Wellness Center', 8),

    -- Hotels & Accommodations
    ('hotels',           'business', 'hotels-accom', 'Hotels',           1),
    ('motels',           'business', 'hotels-accom', 'Motels',           2),
    ('inns',             'business', 'hotels-accom', 'Inns',             3),
    ('pension-houses',   'business', 'hotels-accom', 'Pension Houses',   4),
    ('resorts',          'business', 'hotels-accom', 'Resorts',          5),
    ('lodging-houses',   'business', 'hotels-accom', 'Lodging Houses',   6),
    ('bed-and-breakfast','business', 'hotels-accom', 'Bed & Breakfast',  7),

    -- Transportation
    ('bus-terminal',        'business', 'transportation', 'Bus Terminal',        1),
    ('tricycle-terminal',   'business', 'transportation', 'Tricycle Terminal',   2),
    ('jeepney-terminal',    'business', 'transportation', 'Jeepney Terminal',    3),
    ('taxi-stand',          'business', 'transportation', 'Taxi Stand',          4),
    ('transport-services',  'business', 'transportation', 'Transport Services', 5),
    ('fuel-stations',       'business', 'transportation', 'Fuel Stations',       6),
    ('ev-charging-stations','business', 'transportation', 'EV Charging Stations',7),
    ('parking-areas',       'business', 'transportation', 'Parking Areas',       8),

    -- Finance & Banking
    ('banks',                'business', 'finance-banking', 'Banks',                1),
    ('atms',                 'business', 'finance-banking', 'ATMs',                 2),
    ('lending-institutions', 'business', 'finance-banking', 'Lending Institutions', 3),
    ('cooperatives',         'business', 'finance-banking', 'Cooperatives',         4),
    ('remittance-centers',   'business', 'finance-banking', 'Remittance Centers',   5),
    ('payment-centers',      'business', 'finance-banking', 'Payment Centers',      6),
    ('insurance-offices',    'business', 'finance-banking', 'Insurance Offices',    7),
    ('pawnshops',            'business', 'finance-banking', 'Pawnshops',            8)
ON CONFLICT (id) DO NOTHING;

-- ── Seed: Map Locations (module = 'map') — 6 groups ───────────────────────
INSERT INTO directory_category_groups (id, module, name, icon, color, display_order) VALUES
    ('map-government',       'map', 'Government',         '🏛', 'blue', 1),
    ('map-healthcare',       'map', 'Healthcare',          '🏥', 'red',  2),
    ('map-education',        'map', 'Education',           '🎓', 'gold', 3),
    ('map-tourism',          'map', 'Tourism',              '🏖', 'teal', 4),
    ('map-parks-recreation', 'map', 'Parks & Recreation',  '🌳', 'blue', 5),
    ('map-transportation',   'map', 'Transportation',      '🚍', 'gold', 6)
ON CONFLICT (id) DO NOTHING;

INSERT INTO directory_subcategories (id, module, group_id, name, display_order) VALUES
    ('map-barangay-hall',      'map', 'map-government', 'Barangay Hall',    1),
    ('map-municipal-office',   'map', 'map-government', 'Municipal Office', 2),
    ('map-police-station',     'map', 'map-government', 'Police Station',   3),
    ('map-fire-station',       'map', 'map-government', 'Fire Station',     4),

    ('map-hospital',           'map', 'map-healthcare', 'Hospital',       1),
    ('map-health-center',      'map', 'map-healthcare', 'Health Center',  2),
    ('map-medical-clinic',     'map', 'map-healthcare', 'Medical Clinic', 3),

    ('map-elementary-school',  'map', 'map-education', 'Elementary School', 1),
    ('map-high-school',        'map', 'map-education', 'High School',       2),
    ('map-college',            'map', 'map-education', 'College',           3),

    ('map-tourist-attraction', 'map', 'map-tourism', 'Tourist Attraction',  1),
    ('map-historical-landmark','map', 'map-tourism', 'Historical Landmark', 2),
    ('map-cultural-site',      'map', 'map-tourism', 'Cultural Site',       3),

    ('map-public-park',       'map', 'map-parks-recreation', 'Public Park',     1),
    ('map-playground',        'map', 'map-parks-recreation', 'Playground',      2),
    ('map-sports-complex',    'map', 'map-parks-recreation', 'Sports Complex',  3),

    ('map-bus-terminal',      'map', 'map-transportation', 'Bus Terminal',      1),
    ('map-tricycle-terminal', 'map', 'map-transportation', 'Tricycle Terminal', 2),
    ('map-jeepney-terminal',  'map', 'map-transportation', 'Jeepney Terminal',  3)
ON CONFLICT (id) DO NOTHING;

-- ── Seed: Organization Directory (module = 'organization') — 7 groups ─────
INSERT INTO directory_category_groups (id, module, name, icon, color, display_order) VALUES
    ('org-government',  'organization', 'Government Organizations',     '🏛', 'blue', 1),
    ('org-community',   'organization', 'Community Organizations',      '🤝', 'teal', 2),
    ('org-youth',        'organization', 'Youth Organizations',          '🧑‍🤝‍🧑', 'gold', 3),
    ('org-senior',       'organization', 'Senior Citizen Organizations', '👴', 'red',  4),
    ('org-women',        'organization', 'Women''s Organizations',       '👩', 'blue', 5),
    ('org-religious',    'organization', 'Religious Organizations',     '⛪', 'teal', 6),
    ('org-volunteer',    'organization', 'Volunteer Organizations',     '🙋', 'gold', 7)
ON CONFLICT (id) DO NOTHING;

INSERT INTO directory_subcategories (id, module, group_id, name, display_order) VALUES
    ('org-barangay-council',    'organization', 'org-government', 'Barangay Council',     1),
    ('org-sk-council',          'organization', 'org-government', 'SK Council',            2),
    ('org-barangay-committees', 'organization', 'org-government', 'Barangay Committees',   3),

    ('org-homeowners-association', 'organization', 'org-community', 'Homeowners Association', 1),
    ('org-peoples-organization',   'organization', 'org-community', 'People''s Organization',  2),
    ('org-cooperative',            'organization', 'org-community', 'Cooperative',             3),

    ('org-youth-club',   'organization', 'org-youth', 'Youth Club',  1),
    ('org-sports-club',  'organization', 'org-youth', 'Sports Club', 2),

    ('org-senior-citizens-association', 'organization', 'org-senior', 'Senior Citizens Association', 1),

    ('org-womens-association', 'organization', 'org-women', 'Women''s Association', 1),

    ('org-church-ministry',  'organization', 'org-religious', 'Church Ministry', 1),
    ('org-religious-group',  'organization', 'org-religious', 'Religious Group',  2),

    ('org-volunteer-group',    'organization', 'org-volunteer', 'Volunteer Group',    1),
    ('org-civic-organization', 'organization', 'org-volunteer', 'Civic Organization', 2)
ON CONFLICT (id) DO NOTHING;

-- ── Seed: Emergency Directory (module = 'emergency') — 6 groups ───────────
INSERT INTO directory_category_groups (id, module, name, icon, color, display_order) VALUES
    ('em-police',       'emergency', 'Police',             '🚓', 'blue', 1),
    ('em-fire-rescue',  'emergency', 'Fire & Rescue',      '🚒', 'red',  2),
    ('em-medical',      'emergency', 'Medical Emergency',  '🏥', 'teal', 3),
    ('em-disaster',     'emergency', 'Disaster Response',  '📡', 'gold', 4),
    ('em-utilities',    'emergency', 'Utilities',          '🔌', 'blue', 5),
    ('em-hotlines',     'emergency', 'Emergency Hotlines', '📞', 'red',  6)
ON CONFLICT (id) DO NOTHING;

INSERT INTO directory_subcategories (id, module, group_id, name, display_order) VALUES
    ('em-police-station', 'emergency', 'em-police', 'Police Station', 1),
    ('em-police-hotline',  'emergency', 'em-police', 'Police Hotline', 2),

    ('em-fire-station',  'emergency', 'em-fire-rescue', 'Fire Station', 1),
    ('em-rescue-team',   'emergency', 'em-fire-rescue', 'Rescue Team',  2),
    ('em-bert',          'emergency', 'em-fire-rescue', 'BERT',         3),

    ('em-hospital',       'emergency', 'em-medical', 'Hospital',      1),
    ('em-ambulance',      'emergency', 'em-medical', 'Ambulance',     2),
    ('em-health-center',  'emergency', 'em-medical', 'Health Center', 3),

    ('em-mdrrmo',            'emergency', 'em-disaster', 'MDRRMO',            1),
    ('em-evacuation-center', 'emergency', 'em-disaster', 'Evacuation Center', 2),

    ('em-electric-utility', 'emergency', 'em-utilities', 'Electric Utility', 1),
    ('em-water-utility',    'emergency', 'em-utilities', 'Water Utility',    2),

    ('em-hotline-national', 'emergency', 'em-hotlines', 'National', 1),
    ('em-hotline-local',    'emergency', 'em-hotlines', 'Local',     2)
ON CONFLICT (id) DO NOTHING;

-- Disable RLS so the server-side Python client (service role) can read/write freely.
-- This matches the setup of all other tables in this project.
ALTER TABLE directory_category_groups DISABLE ROW LEVEL SECURITY;
ALTER TABLE directory_subcategories DISABLE ROW LEVEL SECURITY;
