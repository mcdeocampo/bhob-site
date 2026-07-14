-- Migration: seed the 11 public services currently hardcoded in services.html
-- Run this immediately after create_public_services.sql so the site's
-- existing content survives the CMS cutover. IDs are fixed, readable slugs
-- (not the uuid4().hex format the app generates for new rows going forward)
-- purely so this file is self-contained and re-runnable; the app treats the
-- id column as opaque TEXT either way.
-- Safe to re-run: ON CONFLICT DO NOTHING.

INSERT INTO public_services
    (id, title, short_description, description, icon_type, icon,
     processing_time, fee, office, status, display_order)
VALUES
    ('svc-clearance', 'Barangay Clearance',
     'Official certification for legal, employment, business, or personal purposes.',
     'Official certification for legal, employment, business, or personal purposes.',
     'preset', 'clearance', 'Same day to 1 working day', 'Based on approved barangay schedule',
     'Barangay Secretary', 'published', 0),

    ('svc-residency', 'Certificate of Residency',
     'Proof that the applicant is a resident of Barangay Hulo.',
     'Proof that the applicant is a resident of Barangay Hulo.',
     'preset', 'residency', 'Same day', 'May be free or based on ordinance',
     'Barangay Secretary', 'published', 1),

    ('svc-indigency', 'Certificate of Indigency',
     'Certification for residents requesting assistance or benefits.',
     'Certification for residents requesting assistance or benefits.',
     'preset', 'indigency', '1 working day', 'Usually free',
     'Punong Barangay / Barangay Secretary', 'published', 2),

    ('svc-business', 'Business Clearance',
     'Barangay endorsement for business permit processing.',
     'Barangay endorsement for business permit processing.',
     'preset', 'business', '1-2 working days', 'Based on ordinance',
     'Barangay Treasurer', 'published', 3),

    ('svc-jobseeker', 'First Time Jobseeker Certificate',
     'Certificate for eligible first-time jobseekers.',
     'Certificate for eligible first-time jobseekers.',
     'preset', 'jobseeker', 'Same day to 1 working day', 'Free for qualified applicants',
     'Barangay Secretary', 'published', 4),

    ('svc-blotter', 'Blotter / Complaint Assistance',
     'Recording and assistance for complaints, incidents, and mediation.',
     'Recording and assistance for complaints, incidents, and mediation.',
     'preset', 'blotter', 'Depends on case', 'Free',
     'Barangay Desk Officer', 'published', 5),

    ('svc-health', 'Health Assistance',
     'Basic health support and referral assistance.',
     'Basic health support and referral assistance.',
     'preset', 'health', 'As scheduled', 'Free',
     'Barangay Health Workers', 'published', 6),

    ('svc-senior', 'Senior Citizen Assistance',
     'Support and coordination for senior citizen concerns.',
     'Support and coordination for senior citizen concerns.',
     'preset', 'senior', 'As scheduled', 'Free',
     'Senior Citizen Desk', 'published', 7),

    ('svc-pwd', 'PWD Assistance',
     'Assistance and coordination for persons with disabilities.',
     'Assistance and coordination for persons with disabilities.',
     'preset', 'pwd', 'As scheduled', 'Free',
     'PWD Desk', 'published', 8),

    ('svc-disaster', 'Disaster Response Assistance',
     'Urgent support during emergencies, floods, fires, and disasters.',
     'Urgent support during emergencies, floods, fires, and disasters.',
     'preset', 'disaster', 'Immediate response', 'Free',
     'BDRRMC / Tanods', 'published', 9),

    ('svc-youth', 'SK Youth Programs',
     'Youth activities, sports, leadership, and development programs.',
     'Youth activities, sports, leadership, and development programs.',
     'preset', 'youth', 'As scheduled', 'Free',
     'SK Chairperson', 'published', 10)
ON CONFLICT (id) DO NOTHING;

INSERT INTO public_service_requirements (id, service_id, requirement, display_order) VALUES
    ('svc-clearance-req-1', 'svc-clearance', 'Valid ID', 0),
    ('svc-clearance-req-2', 'svc-clearance', 'Proof of residence', 1),
    ('svc-clearance-req-3', 'svc-clearance', 'Accomplished request form', 2),

    ('svc-residency-req-1', 'svc-residency', 'Valid ID', 0),
    ('svc-residency-req-2', 'svc-residency', 'Proof of address', 1),

    ('svc-indigency-req-1', 'svc-indigency', 'Valid ID', 0),
    ('svc-indigency-req-2', 'svc-indigency', 'Interview / verification', 1),
    ('svc-indigency-req-3', 'svc-indigency', 'Proof of need', 2),

    ('svc-business-req-1', 'svc-business', 'Business details', 0),
    ('svc-business-req-2', 'svc-business', 'Valid ID', 1),
    ('svc-business-req-3', 'svc-business', 'Lease / proof of location', 2),

    ('svc-jobseeker-req-1', 'svc-jobseeker', 'Valid ID', 0),
    ('svc-jobseeker-req-2', 'svc-jobseeker', 'Oath of undertaking', 1),
    ('svc-jobseeker-req-3', 'svc-jobseeker', 'Residency proof', 2),

    ('svc-blotter-req-1', 'svc-blotter', 'Valid ID', 0),
    ('svc-blotter-req-2', 'svc-blotter', 'Incident details', 1),

    ('svc-health-req-1', 'svc-health', 'Valid ID', 0),
    ('svc-health-req-2', 'svc-health', 'Health concern details', 1),

    ('svc-senior-req-1', 'svc-senior', 'Senior citizen ID', 0),
    ('svc-senior-req-2', 'svc-senior', 'Request details', 1),

    ('svc-pwd-req-1', 'svc-pwd', 'PWD ID or supporting documents', 0),

    ('svc-disaster-req-1', 'svc-disaster', 'Incident details', 0),
    ('svc-disaster-req-2', 'svc-disaster', 'Location', 1),

    ('svc-youth-req-1', 'svc-youth', 'Age / residency details when required', 0)
ON CONFLICT (id) DO NOTHING;
