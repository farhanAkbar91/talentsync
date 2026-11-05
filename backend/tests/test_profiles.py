"""Pengujian profil kandidat & perusahaan."""


def test_candidate_profile_auto_created_empty(client):
    _, headers = __import__("tests.helpers", fromlist=["make_candidate"]).make_candidate(client)
    resp = client.get("/api/v1/me/candidate-profile", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["skills"] == []
    assert body["education"] == []


def test_candidate_profile_update(client):
    from tests.helpers import make_candidate

    _, headers = make_candidate(client, email="profil@example.com")
    payload = {
        "full_name": "Sarah Wijaya",
        "phone": "+62 812-3456-7890",
        "location": "Jakarta Selatan",
        "headline": "Senior UI/UX Designer",
        "summary": "Desainer produk dengan fokus sistem desain.",
        "skills": ["Figma", "figma", "Design System", "  "],
        "education": [
            {
                "school": "Universitas Airlangga",
                "degree": "S1",
                "start_year": 2019,
                "end_year": 2023,
            }
        ],
        "experience": [
            {
                "company": "PT Maju",
                "title": "Product Designer",
                "start_period": "2023-01",
                "end_period": "sekarang",
            }
        ],
        "certifications": [{"name": "SUS & Usability", "issuer": "NN/g", "year": 2024}],
        "links": {"linkedin": "linkedin.com/in/sarahwijaya", "portfolio": "sarah.design"},
    }
    resp = client.put("/api/v1/me/candidate-profile", json=payload, headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["skills"] == ["Figma", "Design System"]  # dedupe + strip
    assert body["education"][0]["school"] == "Universitas Airlangga"

    # full_name ikut terbarui di akun
    me = client.get("/api/v1/auth/me", headers=headers).json()
    assert me["full_name"] == "Sarah Wijaya"

    # Persisten
    again = client.get("/api/v1/me/candidate-profile", headers=headers).json()
    assert again["headline"] == "Senior UI/UX Designer"


def test_candidate_profile_invalid_education_rejected(client):
    from tests.helpers import make_candidate

    _, headers = make_candidate(client)
    resp = client.put(
        "/api/v1/me/candidate-profile",
        json={"full_name": "Budi", "education": [{"school": ""}]},
        headers=headers,
    )
    assert resp.status_code == 422


def test_company_create_once_then_conflict(client):
    from tests.helpers import make_hr_with_company

    reg, headers, company = make_hr_with_company(client, company_name="PT Satu")
    assert company["name"] == "PT Satu"

    resp = client.post("/api/v1/me/company", json={"name": "PT Dua"}, headers=headers)
    assert resp.status_code == 409


def test_company_get_before_create_404(client):
    from tests.helpers import auth_headers, register

    reg = register(client, role="hr")
    resp = client.get("/api/v1/me/company", headers=auth_headers(reg))
    assert resp.status_code == 404


def test_company_update(client):
    from tests.helpers import make_hr_with_company

    reg, headers, _ = make_hr_with_company(client)
    resp = client.put(
        "/api/v1/me/company",
        json={
            "name": "PT Teknologi Maju",
            "description": "Perusahaan SaaS B2B.",
            "website": "https://maju.example.id",
            "contact_email": "hr@maju.example.id",
        },
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["website"] == "https://maju.example.id"
