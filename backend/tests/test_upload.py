import unittest
from unittest.mock import patch, MagicMock
from flask import Flask
from models import db, Upload
from api.upload import upload_file
from tasks import process_upload

class TestUploadLogic(unittest.TestCase):
    def setUp(self):
        # Set up a test Flask app and database
        self.app = Flask(__name__)
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.app.config['TESTING'] = True
        db.init_app(self.app)
        with self.app.app_context():
            db.create_all()

    def tearDown(self):
        # Clean up the database
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    @patch('api.upload.request')
    def test_upload_file(self, mock_request):
        # Mock the request to simulate file upload
        mock_request.files = {'file': MagicMock(filename='test.pdf', read=lambda: b'Test content')}
        mock_request.form = {}
        mock_request.user_id = 'test_user_id'

        with self.app.app_context():
            response = upload_file()
            self.assertEqual(response.status_code, 202)
            self.assertIn('session_id', response.json)

    @patch('tasks.extract_text_from_file', return_value='Extracted text')
    @patch('tasks.analyze_content', return_value={'main_topic': 'Test Topic', 'subtopics': []})
    @patch('tasks.generate_flashcards', return_value=[{'question': 'Q1', 'answer': 'A1'}])
    @patch('tasks.generate_test_questions', return_value=[{'text': 'Q1', 'options': ['A', 'B'], 'correct': 0}])
    def test_process_upload(self, mock_extract, mock_analyze, mock_flashcards, mock_questions):
        # Test the process_upload task
        with self.app.app_context():
            result = process_upload('test_session_id', [('test.pdf', b'Test content')], 'test_user_id')
            self.assertIn('flashcards', result)
            self.assertIn('questions', result)
            self.assertEqual(len(result['flashcards']), 1)
            self.assertEqual(len(result['questions']), 1)

if __name__ == '__main__':
    unittest.main() 