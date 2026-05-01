#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import auth_manager
import ubicast_course_downloader as ucd


class ExtractorTests(unittest.TestCase):
    def test_extract_course_title_prefers_h1(self):
        html = "<html><head><title>Titre page</title></head><body><h1>Cours Test</h1></body></html>"
        self.assertEqual(ucd.extract_course_title(html, "https://coursenligne.parisnanterre.fr/course/view.php?id=12"), "Cours Test")

    def test_extract_activity_links_dedupes_in_order(self):
        html = """
        <a href="/mod/ubicast/view.php?id=1">A</a>
        <a href="https://coursenligne.parisnanterre.fr/mod/ubicast/view.php?id=1">A</a>
        <a href="/mod/ubicast/view.php?id=2">B</a>
        """
        links = ucd.extract_activity_links(html, "https://coursenligne.parisnanterre.fr/course/view.php?id=12")
        self.assertEqual([ucd.activity_id(link) for link in links], ["1", "2"])

    def test_extract_webtv_urls_from_iframe_and_raw_text(self):
        html = """
        <iframe src="https://webtv.parisnanterre.fr/videos/abc"></iframe>
        "https://webtv.parisnanterre.fr/videos/def"
        """
        urls = ucd.extract_webtv_urls(html, "https://coursenligne.parisnanterre.fr/mod/ubicast/view.php?id=1")
        self.assertEqual(urls[0], "https://webtv.parisnanterre.fr/videos/abc")
        self.assertIn("https://webtv.parisnanterre.fr/videos/def", urls)

    def test_extract_vtt_urls_from_track_and_subtitle_hint(self):
        html = """
        <track src="/protected/videos/a/subtitles/subtitle_fr.vtt">
        {"url": "/protected/videos/b/subtitles/subtitle_en.vtt"}
        """
        urls = ucd.extract_vtt_urls(html, "https://webtv.parisnanterre.fr/player/1")
        self.assertIn("https://webtv.parisnanterre.fr/protected/videos/a/subtitles/subtitle_fr.vtt", urls)
        self.assertIn("https://webtv.parisnanterre.fr/protected/videos/b/subtitles/subtitle_en.vtt", urls)

    def test_extract_launch_urls(self):
        html = '<iframe src="/mod/ubicast/launch.php?id=219186&mediaid=vabc"></iframe>'
        urls = ucd.extract_launch_urls(html, "https://coursenligne.parisnanterre.fr/mod/ubicast/view.php?id=219186")
        self.assertEqual(urls, ["https://coursenligne.parisnanterre.fr/mod/ubicast/launch.php?id=219186&mediaid=vabc"])

    def test_extract_lti_form(self):
        html = """
        <form action="https://webtv.parisnanterre.fr/lti/vabc/" method="post">
          <input type="hidden" name="oauth_nonce" value="nonce">
          <input type="hidden" name="resource_link_id" value="link">
        </form>
        """
        action, fields = ucd.extract_lti_form(html, "https://coursenligne.parisnanterre.fr/mod/ubicast/launch.php?id=1")
        self.assertEqual(action, "https://webtv.parisnanterre.fr/lti/vabc/")
        self.assertEqual(fields["oauth_nonce"], "nonce")

    def test_validate_vtt_accepts_bom(self):
        self.assertTrue(ucd.validate_vtt(b"\xef\xbb\xbfWEBVTT\n\n1\n"))
        self.assertFalse(ucd.validate_vtt(b"<html>Authentification requise</html>"))

    def test_detects_cas_login_page(self):
        html = "<title>CAS - Central Authentication Service Connexion</title>"
        url = "https://cas.parisnanterre.fr/login?service=https%3A%2F%2Fcoursenligne.parisnanterre.fr%2Flogin%2Findex.php"
        self.assertTrue(ucd.is_login_page(html, url))

    def test_cookie_header_builds_cookie_string(self):
        cookies = [{"name": "MoodleSession", "value": "abc"}, {"name": "theme", "value": "boost"}]
        self.assertEqual(auth_manager._cookie_header(cookies), "MoodleSession=abc; theme=boost")

    def test_write_runtime_env_is_runtime_local(self):
        with TemporaryDirectory() as tmp:
            auth_manager.write_runtime_env({"MOODLE_COOKIE": "MoodleSession=abc"}, tmp)
            env_path = Path(tmp) / ".env"
            self.assertTrue(env_path.exists())
            self.assertIn("MOODLE_COOKIE=", env_path.read_text(encoding="utf-8"))

    def test_process_course_url_exists_for_gui(self):
        self.assertTrue(callable(ucd.process_course_url))
        self.assertIsNone(ucd.last_course_dir())


if __name__ == "__main__":
    unittest.main()
