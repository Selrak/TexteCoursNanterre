#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import unittest

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

    def test_validate_vtt_accepts_bom(self):
        self.assertTrue(ucd.validate_vtt(b"\xef\xbb\xbfWEBVTT\n\n1\n"))
        self.assertFalse(ucd.validate_vtt(b"<html>Authentification requise</html>"))

    def test_detects_cas_login_page(self):
        html = "<title>CAS - Central Authentication Service Connexion</title>"
        url = "https://cas.parisnanterre.fr/login?service=https%3A%2F%2Fcoursenligne.parisnanterre.fr%2Flogin%2Findex.php"
        self.assertTrue(ucd.is_login_page(html, url))


if __name__ == "__main__":
    unittest.main()
