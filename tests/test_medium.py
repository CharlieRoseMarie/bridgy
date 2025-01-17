# coding=utf-8
"""Unit tests for medium.py.
"""
from __future__ import unicode_literals
from __future__ import absolute_import

from future import standard_library
standard_library.install_aliases()
import urllib.request, urllib.parse, urllib.error

import appengine_config
from oauth_dropins import medium as oauth_medium
from oauth_dropins.webutil.util import json_dumps, json_loads

from medium import ChooseBlog, Medium, application
from . import testutil


USER = {
  'data': {
    'id': 'abcdef01234',
    'username': 'ry',
    'name': 'Ryan',
    'url': 'http://medium.com/@ry',
    'imageUrl': 'http://ava/tar',
  },
}
PUBLICATIONS = {
  'data': [{
    'id': 'b969ac62a46b',
    'name': 'About Medium',
    'description': 'What is this thing and how does it work?',
    'url': 'https://medium.com/about',
    'imageUrl': 'https://about/image.png'
  }, {
    'id': 'b45573563f5a',
    'name': 'Developers',
    'description': 'Medium’s Developer resources',
    'url': 'https://medium.com/developers',
    'imageUrl': 'https://developers/image.png'
  }],
}

class MediumTest(testutil.HandlerTest):

  def setUp(self):
    super(MediumTest, self).setUp()
    self.auth_entity = oauth_medium.MediumAuth(
      id='abcdef01234', access_token_str='my token', user_json=json_dumps(USER),
      publications_json=json_dumps(PUBLICATIONS))
    self.auth_entity.put()

    # prevent subscribing to superfeedr
    self.orig_debug = appengine_config.DEBUG
    appengine_config.DEBUG = True

  def tearDown(self):
    appengine_config.DEBUG = self.orig_debug

  def expect_requests_get(self, path, *args, **kwargs):
    return super(testutil.HandlerTest, self).expect_requests_get(
      oauth_medium.API_BASE + path,
      *args,
      headers={
        'Authorization': 'Bearer my token',
        'User-Agent': oauth_medium.USER_AGENT,
      },
      **kwargs)

  def expect_get_publications(self, pubs):
    # https://github.com/Medium/medium-api-docs/#user-content-listing-the-users-publications
    self.expect_requests_get('users/abcdef01234/publications', json_dumps(pubs))
    self.mox.ReplayAll()

  def assert_created_profile(self, medium=None):
    if not medium:
      mediums = list(Medium.query())
      self.assertEquals(1, len(mediums))
      medium = mediums[0]

    self.assertEquals('@ry', medium.key.id())
    self.assertEquals(self.auth_entity.key, medium.auth_entity)
    self.assertEquals('Ryan', medium.name)
    self.assertEquals('http://medium.com/@ry', medium.url)
    self.assertEquals('http://ava/tar', medium.picture)
    self.assertFalse(medium.is_publication())
    self.assertEquals('http://medium.com/feed/@ry', medium.feed_url())
    self.assertEquals('http://medium.com/@ry', medium.silo_url())

  def assert_created_publication(self, medium=None):
    if not medium:
      mediums = list(Medium.query())
      self.assertEquals(1, len(mediums))
      medium = mediums[0]

    self.assertEquals('b45573563f5a', medium.key.id())
    self.assertEquals(self.auth_entity.key, medium.auth_entity)
    self.assertEquals('Developers', medium.name)
    self.assertEquals('https://medium.com/developers', medium.url)
    self.assertEquals('https://developers/image.png', medium.picture)
    self.assertTrue(medium.is_publication())
    self.assertEquals('https://medium.com/feed/developers', medium.feed_url())
    self.assertEquals('https://medium.com/developers', medium.silo_url())

  def test_new_profile(self):
    self.assert_created_profile(
      Medium.new(self.handler, auth_entity=self.auth_entity, id='@ry'))

  def test_new_publication(self):
    self.assert_created_publication(
      Medium.new(self.handler, auth_entity=self.auth_entity, id='b45573563f5a'))

  def test_choose_blog_decline(self):
    ChooseBlog(self.request, self.response).finish(None)
    self.assertEquals(0, Medium.query().count())
    self.assertEquals(302, self.response.status_int)
    self.assertEquals(
      "http://localhost/#!OK, you're not signed up. Hope you reconsider!",
      urllib.parse.unquote_plus(self.response.headers['Location']))

  def test_choose_blog_no_publications(self):
    self.expect_get_publications({})
    ChooseBlog(self.request, self.response).finish(self.auth_entity)
    self.assertEquals(302, self.response.status_int)
    loc = urllib.parse.unquote_plus(self.response.headers['Location'])
    self.assertTrue(loc.startswith('http://localhost/'), loc)
    self.assert_created_profile()

  def test_choose_blog_publications(self):
    self.expect_get_publications(PUBLICATIONS)
    ChooseBlog(self.request, self.response).finish(self.auth_entity)
    self.assert_equals(200, self.response.status_code)
    for expected in ('action="/medium/add" method="post"',
                     '<input type="radio" name="blog" id="@ry"',
                     '<input type="radio" name="blog" id="b969ac62a46b"',
                     '<input type="radio" name="blog" id="b45573563f5a"',
                     ):
      self.assertIn(expected, self.response.text)

    self.assertEquals(0, Medium.query().count())

  def test_add_profile(self):
    resp = application.get_response(
      '/medium/add?auth_entity_key=%s&state={"feature":"webmention"}&blog=@ry' %
      self.auth_entity.key.urlsafe(),
      method='POST')

    self.assertEquals(302, resp.status_int)
    loc = urllib.parse.unquote_plus(resp.headers['Location'])
    self.assertTrue(loc.startswith('http://localhost/'), loc)
    self.assert_created_profile()

  def test_add_publication(self):
    resp = application.get_response(
      '/medium/add?auth_entity_key=%s&state={"feature":"webmention"}&blog=b45573563f5a' %
      self.auth_entity.key.urlsafe(),
      method='POST')

    self.assertEquals(302, resp.status_int)
    loc = urllib.parse.unquote_plus(resp.headers['Location'])
    self.assertTrue(loc.startswith('http://localhost/'), loc)
    self.assert_created_publication()
