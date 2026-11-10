import copy
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from ai.client import AIClient
from core.config import Config

class StatusError(Exception):
    def __init__(self,status,param=None,message='error'):
        self.status_code=status
        self.body=dict(param=param,message=message)

def client_for(events,mode='auto'):
    calls=[]
    def create(**kwargs):
        calls.append(copy.deepcopy(kwargs))
        event=events.pop(0)
        if isinstance(event,Exception):raise event
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=event),finish_reason='stop')])
    client=AIClient.__new__(AIClient)
    client.config=Config(ai_json_mode=mode)
    client.cancel_check=lambda:False
    client._client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return client,calls

class ClientTests(unittest.TestCase):
    def test_json_auto_fallback_and_strict_mode(self):
        error=StatusError(400,'response_format','response_format is unsupported')
        client,calls=client_for([error,'{}'])
        self.assertEqual(client.chat('JSON','JSON',True),'{}')
        self.assertIn('response_format',calls[0])
        self.assertNotIn('response_format',calls[1])
        client,calls=client_for([error],'force')
        with self.assertRaises(RuntimeError):client.chat('JSON','JSON',True)
        self.assertEqual(len(calls),1)

    def test_parameter_compatibility_and_permanent_error(self):
        client,calls=client_for([StatusError(400,'max_tokens','max_tokens is not supported'),StatusError(400,'temperature','temperature is unsupported'),'{}'])
        self.assertEqual(client.chat('JSON','JSON',True),'{}')
        self.assertIn('max_completion_tokens',calls[-1])
        self.assertNotIn('temperature',calls[-1])
        client,calls=client_for([StatusError(401,message='sensitive remote body')])
        with self.assertRaises(RuntimeError) as result:client.chat('JSON','JSON',True)
        self.assertNotIn('sensitive',str(result.exception))
        self.assertEqual(len(calls),1)

    def test_transient_retry_and_cancellation(self):
        client,calls=client_for([StatusError(503),'{}'])
        ticks=iter(range(100))
        with patch('ai.client.time.monotonic',side_effect=lambda:next(ticks)),patch('ai.client.time.sleep'),patch('ai.client.random.random',return_value=0):
            self.assertEqual(client.chat('JSON','JSON',True),'{}')
        self.assertEqual(len(calls),2)
        client,calls=client_for(['{}'])
        client.cancel_check=lambda:True
        with self.assertRaises(RuntimeError):client.chat('JSON','JSON',True)
        self.assertEqual(calls,[])

if __name__=='__main__':unittest.main()
