from database.repos import ScanRepository


def test_add_favorite(tmp_path):
    db = tmp_path / "favorites.db"
    repo = ScanRepository(db)

    payload = {
        "slug": "akismet",
        "name": "Akismet",
        "version": "1.0.0",
        "score": 80,
        "installations": 1000,
        "days_since_update": 5,
        "tested_wp_version": "6.8",
        "is_theme": False,
        "download_link": "https://downloads.wordpress.org/plugin/akismet.zip",
        "wp_org_link": "https://wordpress.org/plugins/akismet/",
        "cve_search_link": "https://cve.mitre.org/cgi-bin/cvekey.cgi?keyword=akismet",
        "wpscan_link": "https://wpscan.com/plugin/akismet",
        "trac_link": "https://plugins.trac.wordpress.org/browser/akismet/",
        "author_trusted": False,
        "is_risky_category": False,
        "is_user_facing": True,
        "risk_tags": ["public-input"],
        "security_flags": ["custom-ajax"],
        "feature_flags": ["settings-page"],
        "code_analysis": {"summary": "ok"},
    }

    assert repo.add_favorite(payload) is True

    favs = repo.get_favorites()
    assert len(favs) == 1
    assert favs[0]["slug"] == "akismet"
    assert favs[0]["feature_flags"] == ["settings-page"]
    assert favs[0]["code_analysis"]["summary"] == "ok"
