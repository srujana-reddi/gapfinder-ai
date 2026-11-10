import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
(ROOT / 'instance').mkdir(exist_ok=True)
TEST_DATA = tempfile.TemporaryDirectory(dir=ROOT / 'instance')
os.environ['GAPFINDER_DATA_DIR'] = TEST_DATA.name
with patch.dict(os.environ, {'DATABASE_URL': '', 'POSTGRES_URL': '', 'VERCEL': ''}):
    import app as module
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
import rag

class AppTests(unittest.TestCase):
    def setUp(self):
        self.client = module.app.test_client()
        self.csrf = self.client.get('/api/session').json['csrf']
        email = module.uid() + '@test.local'
        self.post('/register', {'name':'Student','email':email,'password':'Testing123!'} )
        result = self.post('/login', {'email':email,'password':'Testing123!'})
        self.csrf = result.json['csrf']

    def post(self, path, data):
        return self.client.post('/api'+path, json=data, headers={'X-CSRF-Token':self.csrf})

    def state(self):
        return self.client.get('/api/state').json

    def load(self):
        existing = {doc['name'] for doc in self.state()['documents']}
        for filename, kind in [('syllabus.txt', 'syllabus'), ('notes.txt', 'notes'), ('past-paper.txt', 'paper')]:
            if filename not in existing:
                response = self.upload(filename, (ROOT / 'sample-materials' / filename).read_bytes(), kind)
                self.assertEqual(response.status_code, 200)

    def test_topic_parser_excludes_qa_and_wrapped_answers(self):
        text = ('Page 1\nPython OOP    Machine Learning    NLP Fundamentals\n'
                '1. What is inheritance?\nAnswer: Inheritance lets a subclass reuse code.\n'
                'Use it for reuse\n2. What is polymorphism?')
        self.assertEqual(module.broad_topics(text), ['Python OOP', 'Machine Learning', 'NLP Fundamentals'])

    def test_full_learning_loop_and_adaptation(self):
        self.load()
        initial = self.state()
        self.assertEqual(len(initial['topics']), 6)
        self.assertTrue(all(t['level']=='untested' for t in initial['topics']))
        self.assertEqual(len(initial['mappings']), 8)
        response = self.post('/quiz', {'count':6,'mode':'demo'})
        self.assertEqual(response.status_code, 200, response.json)
        quiz = response.json
        self.assertTrue(all('answer' not in q for q in quiz['questions']))
        submitted = self.post('/quiz/'+quiz['id']+'/submit', {'answers':{}})
        self.assertEqual(submitted.json['score'], 0)
        weak = self.state()
        self.assertTrue(all(t['level']=='weak' for t in weak['topics']))
        self.assertEqual(self.post('/quiz/'+quiz['id']+'/submit', {'answers':{}}).status_code, 400)
        second = self.post('/quiz', {'count':6,'mode':'demo'}).json
        with self.client.session_transaction() as sess:
            user_id = sess['user_id']
        with module.db() as c:
            saved = __import__('json').loads(c.execute('SELECT state FROM users WHERE id=?',(user_id,)).fetchone()['state'])
        hidden = next(q for q in saved['quizzes'] if q['id']==second['id'])
        answers = {q['id']:q['answer'] for q in hidden['questions']}
        self.assertEqual(self.post('/quiz/'+second['id']+'/submit', {'answers':answers}).json['score'], 100)
        improved = self.state()
        self.assertTrue(all(t['level']=='strong' for t in improved['topics']))
        self.assertTrue(all(len(t['history'])==2 for t in improved['topics']))
        self.assertNotEqual(weak['plan'][0]['id'], improved['plan'][0]['id'])

    def test_time_budget_and_checks(self):
        self.load()
        self.assertEqual(self.post('/settings', {'days':3,'minutes':61}).status_code, 200)
        state = self.state()
        for day in range(1,4):
            self.assertEqual(sum(p['minutes'] for p in state['plan'] if p['day']==day), 61)
        key=state['plan'][0]['id']
        self.post('/plan/check', {'id':key})
        self.assertTrue(self.state()['plan'][0]['done'])
        self.assertEqual(self.post('/settings', {'days':0,'minutes':10}).status_code, 400)

    def test_auth_csrf_and_account_isolation(self):
        self.load()
        other = module.app.test_client()
        self.assertEqual(other.get('/api/state').status_code, 401)
        self.assertEqual(other.post('/api/topics/rebuild',json={}).status_code, 403)
        self.assertEqual(self.client.post('/api/topics/rebuild',json={}).status_code, 403)
        quiz = self.post('/quiz', {'count':1}).json
        email=module.uid()+'@test.local'
        self.post('/register',{'name':'Other','email':email,'password':'Testing123!'})
        res=self.post('/login',{'email':email,'password':'Testing123!'})
        self.csrf=res.json['csrf']
        self.assertEqual(self.state()['documents'], [])
        self.assertEqual(self.client.get('/api/quiz/'+quiz['id']).status_code,400)

    def upload(self,name,content,kind='notes'):
        return self.client.post('/api/upload',data={'kind':kind,'file':(io.BytesIO(content),name)},headers={'X-CSRF-Token':self.csrf})

    def test_text_pdf_upload_and_rejection(self):
        self.assertEqual(self.upload('syllabus.txt',b'Unit 1: Biology\nPhotosynthesis\nCell division','syllabus').status_code,200)
        writer=PdfWriter()
        page=writer.add_blank_page(width=612,height=792)
        font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
        page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
        stream=DecodedStreamObject()
        stream.set_data(b'BT /F1 12 Tf 72 700 Td (Photosynthesis converts light energy into chemical energy in plants.) Tj ET')
        page[NameObject('/Contents')]=writer._add_object(stream)
        out=io.BytesIO();writer.write(out)
        res=self.upload('chapter.pdf',out.getvalue())
        self.assertEqual(res.status_code,200,res.json)
        self.assertEqual(len(self.state()['documents']),2)
        self.assertTrue(any(t['sources'] for t in self.state()['topics']))
        self.assertEqual(self.upload('bad.exe',b'hello').status_code,400)
        self.assertEqual(self.upload('empty.txt',b'').status_code,400)
        self.assertEqual(self.upload('bad.pdf',b'not a pdf').status_code,400)
        blank=PdfWriter();blank.add_blank_page(width=600,height=800);out=io.BytesIO();blank.write(out)
        self.assertIn('OCR',self.upload('scan.pdf',out.getvalue()).json['error'])

    def test_chunked_upload_indexes_only_after_final_part(self):
        transfer = 'a' * 36

        def send(part, content, last):
            return self.client.post('/api/upload/part', data={
                'transfer': transfer, 'part': str(part), 'last': str(last),
                'kind': 'notes', 'file': (io.BytesIO(content), 'chapter.md'),
            }, headers={'X-CSRF-Token': self.csrf})

        self.assertEqual(send(0, b'Machine learning ', 0).status_code, 200)
        self.assertEqual(self.state()['documents'], [])
        self.assertEqual(send(2, b'out of order', 1).status_code, 400)
        self.assertEqual(send(1, b'finds patterns in data.', 1).status_code, 200)
        self.assertEqual([doc['name'] for doc in self.state()['documents']], ['chapter.md'])
        self.assertEqual(send(1, b'duplicate final part', 1).status_code, 400)

    def test_explanations_grounding_and_ai_contract(self):
        self.load()
        self.assertEqual(self.post('/explain',{'question':'quantum chromodynamics'}).json['mode'],'abstained')
        found=self.post('/explain',{'question':'photosynthesis'}).json
        self.assertTrue(found['sources'])
        source=found['sources'][0]
        with patch('rag.generate',return_value={'claims':[{'text':'Supported explanation','source_id':source['id'],'quote':source['text'][:50]}]}):
            res=self.post('/explain',{'question':'photosynthesis','mode':'ai'})
            self.assertEqual(res.status_code,200)
        with patch('rag.generate',return_value={'claims':[{'text':'Unsupported','source_id':'made-up','quote':'made up source quote'}]}):
            self.assertEqual(self.post('/explain',{'question':'photosynthesis','mode':'ai'}).status_code,400)

    def test_ai_generation_grading_and_failure_is_atomic(self):
        self.load()
        topic=self.state()['topics'][0]
        src=topic['sources'][0]
        generated={'prompt':'Explain photosynthesis.','answer':'Light is converted to chemical energy.','source_id':src['id'],'quote':src['text'][:100]}
        with patch('rag.configured',return_value=True),patch('rag.generate',return_value=generated):
            res=self.post('/quiz',{'count':1,'mode':'ai','topic_id':topic['id']})
            self.assertEqual(res.status_code,200,res.json)
        quiz=res.json
        with patch('rag.generate',side_effect=ValueError('Provider unavailable')):
            self.assertEqual(self.post('/quiz/'+quiz['id']+'/submit',{'answers':{quiz['questions'][0]['id']:'My answer'}}).status_code,400)
        self.assertEqual(self.state()['attempts'],[])
        grade={'score':.5,'feedback':'Partially correct; energy conversion is missing.'}
        with patch('rag.generate',return_value=grade):
            res=self.post('/quiz/'+quiz['id']+'/submit',{'answers':{quiz['questions'][0]['id']:'My answer'}})
            self.assertEqual(res.json['score'],50)
            self.assertEqual(res.json['results'][0]['source']['id'],src['id'])
            self.assertEqual(res.json['results'][0]['quote'],generated['quote'])

    def test_demo_idempotent_and_saved_state(self):
        self.load();self.load()
        self.assertEqual(len(self.state()['documents']),3)
        with self.client.session_transaction() as sess:
            ident=sess['user_id']
        with module.db() as c:
            self.assertIn('Photosynthesis',c.execute('SELECT state FROM users WHERE id=?',(ident,)).fetchone()['state'])

    def test_quiz_prerequisites_do_not_call_ai(self):
        with patch('rag.generate') as generate:
            response = self.post('/quiz', {'mode':'demo','count':3})
            self.assertEqual(response.status_code, 400)
            self.assertIn('syllabus and matching notes',response.json['error'])
            self.upload('syllabus.txt',b'Photosynthesis','syllabus')
            self.assertEqual(self.post('/quiz', {'mode':'demo','count':3}).status_code,400)
            self.upload('unrelated.txt',b'Volcanoes erupt molten rock through openings in the crust.')
            self.assertEqual(self.post('/quiz', {'mode':'demo','count':3}).status_code,400)
            generate.assert_not_called()

    def test_reupload_restores_deleted_notes(self):
        self.load()
        notes = next(d for d in self.state()['documents'] if d['kind']=='notes')
        self.client.delete('/api/documents/'+notes['id'],headers={'X-CSRF-Token':self.csrf})
        self.assertFalse(any(t['sources'] for t in self.state()['topics']))
        self.load()
        repaired = self.state()
        self.assertEqual(len(repaired['documents']),3)
        self.assertEqual(len(repaired['topics']),6)
        self.assertTrue(all(t['sources'] for t in repaired['topics']))

class RetrievalTests(unittest.TestCase):
    def test_ranking_and_abstention(self):
        chunks=[{'id':'a','text':'Photosynthesis uses light in chloroplasts.'},{'id':'b','text':'Cell division forms daughter cells.'}]
        self.assertEqual(rag.retrieve('photosynthesis',chunks)[0]['id'],'a')
        self.assertEqual(rag.retrieve('astronomy',chunks),[])

class ProviderTests(unittest.TestCase):
    def test_groq_uses_own_endpoint_and_key(self):
        response = Mock()
        response.json.return_value = {'choices':[{'message':{'content':'{"answer":"grounded"}'}}]}
        with patch.dict(os.environ, {'AI_PROVIDER':'groq','GROQ_API_KEY':'groq-test','XAI_API_KEY':'xai-test'}, clear=True), patch('rag.requests.post',return_value=response) as call:
            self.assertTrue(rag.configured())
            self.assertEqual(rag.generate('test task',[]), {'answer':'grounded'})
            self.assertEqual(call.call_args.args[0], 'https://api.groq.com/openai/v1/chat/completions')
            self.assertEqual(call.call_args.kwargs['headers']['Authorization'], 'Bearer groq-test')
            self.assertEqual(call.call_args.kwargs['json']['model'], 'openai/gpt-oss-20b')
        with patch.dict(os.environ, {'AI_PROVIDER':'groq','XAI_API_KEY':'xai-test'}, clear=True):
            self.assertFalse(rag.configured())

    def test_groq_connection_check(self):
        response=Mock()
        response.json.return_value={'data':[{'id':'openai/gpt-oss-20b'}]}
        with patch.dict(os.environ, {'AI_PROVIDER':'groq','GROQ_API_KEY':'groq-test'}, clear=True), patch('rag.requests.get',return_value=response) as call:
            self.assertTrue(rag.connection_status()['ready'])
            self.assertEqual(call.call_args.args[0], 'https://api.groq.com/openai/v1/models')

    def test_no_credit_error_is_actionable_and_safe(self):
        import requests
        response = requests.Response()
        response.status_code = 403
        response._content = b'{"error":"Your newly created team doesn\'t have any credits or licenses yet. private-team-url secret-key"}'
        with patch.dict(os.environ, {'AI_PROVIDER':'groq','GROQ_API_KEY':'test-key'}, clear=True), patch('rag.requests.get',return_value=response), patch('rag.requests.post',return_value=response):
            status = rag.connection_status()
            self.assertFalse(status['ready'])
            self.assertIn('no API credits',status['message'])
            self.assertNotIn('private-team-url',status['message'])
            self.assertNotIn('secret-key',status['message'])
            with self.assertRaisesRegex(rag.ProviderError,'no API credits'):
                rag.generate('test',[])

    def test_connection_check_validates_model(self):
        response = Mock()
        response.json.return_value = {'data':[{'id':'openai/gpt-oss-20b'}]}
        with patch.dict(os.environ, {'AI_PROVIDER':'groq','GROQ_API_KEY':'test-key','GROQ_MODEL':'openai/gpt-oss-20b'}, clear=True), patch('rag.requests.get',return_value=response):
            self.assertTrue(rag.connection_status()['ready'])
        with patch.dict(os.environ, {'AI_PROVIDER':'groq','GROQ_API_KEY':'test-key','GROQ_MODEL':'missing'}, clear=True), patch('rag.requests.get',return_value=response):
            self.assertFalse(rag.connection_status()['ready'])

if __name__=='__main__':
    unittest.main()
