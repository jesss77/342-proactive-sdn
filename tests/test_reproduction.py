"""Meaningful guards for curated evidence extraction; no live network required."""
from pathlib import Path
import hashlib,importlib.util,json,tempfile,unittest,zipfile
SOURCE=Path(__file__).resolve().parents[1]/'reproduce.py'
spec=importlib.util.spec_from_file_location('reproduce',SOURCE);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
def sha(data):return hashlib.sha256(data).hexdigest()
class EvidenceExtractionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name);self.previous=module.ROOT;module.ROOT=self.base
        (self.base/'data').mkdir();(self.base/'experiment').mkdir();(self.base/'experiment/source.py').write_bytes(b'frozen\n')
    def tearDown(self):module.ROOT=self.previous;self.temp.cleanup()
    def package(self,name='lab/results/runs/sample/metadata.json'):
        payload=b'{"outcome":"failed"}\n';digest=sha(payload)
        with zipfile.ZipFile(self.base/'data/inputs.zip','w') as z:
            z.writestr('index.json',json.dumps(dict(files={name:digest})));z.writestr('objects/'+digest,payload)
        meta=dict(archive_sha256=sha((self.base/'data/inputs.zip').read_bytes()),logical_files=1,frozen_source_files={'source.py':sha(b'frozen\n')})
        (self.base/'data/manifest.json').write_text(json.dumps(meta))
        return payload
    def test_restores_exact_source_and_failed_raw_bytes(self):
        expected=self.package();lab,pub=module.materialize(self.base/'rebuild')
        self.assertEqual((lab/'results/runs/sample/metadata.json').read_bytes(),expected)
        self.assertEqual((lab/'source.py').read_bytes(),b'frozen\n');self.assertEqual((pub/'source.py').read_bytes(),b'frozen\n')
    def test_rejects_corrupt_archive_before_extraction(self):
        self.package();(self.base/'data/inputs.zip').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'archive digest'):module.materialize(self.base/'rebuild')
        self.assertFalse((self.base/'rebuild').exists())
    def test_rejects_changed_frozen_source(self):
        self.package();(self.base/'experiment/source.py').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'Frozen experiment'):module.materialize(self.base/'rebuild')
    def test_rejects_traversal_and_never_writes_outside_inputs(self):
        self.package('lab/../../../escaped.json')
        with self.assertRaisesRegex(ValueError,'Unsafe input path'):module.materialize(self.base/'rebuild')
        self.assertFalse((self.base/'escaped.json').exists())
if __name__=='__main__':unittest.main()
