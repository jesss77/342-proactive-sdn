"""Scientific guards for paper provenance, independent cohorts and displayed cells."""
from pathlib import Path
from copy import deepcopy
import importlib.util,json,tempfile,unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('paper_assets',ROOT/'analysis/build_paper_assets.py')
assets=importlib.util.module_from_spec(spec);spec.loader.exec_module(assets)

class PaperAssetTests(unittest.TestCase):
    def test_v2_duplicate_cell_cannot_inflate_repetitions(self):
        data=json.loads((ROOT/'data/v2/v2-batch.json').read_text());data['completed'][-1]=deepcopy(data['completed'][0])
        with self.assertRaisesRegex(ValueError,'exactly one'):assets.validate_v2(data)

    def test_v2_wrong_plan_order_and_nonfinite_metrics_rejected(self):
        data=json.loads((ROOT/'data/v2/v2-batch.json').read_text());data['completed'].reverse()
        with self.assertRaisesRegex(ValueError,'order'):assets.validate_v2(data)
        data=json.loads((ROOT/'data/v2/v2-batch.json').read_text());data['completed'][0]['udp_loss_percent']=float('nan')
        with self.assertRaisesRegex(ValueError,'Invalid reported'):assets.validate_v2(data)

    def test_hand_changed_table_cell_is_rejected(self):
        table={'metric':{'heads':['Policy','Loss'],'rows':[['ML','0.587']]}}
        changed=deepcopy(table);changed['metric']['rows'][0][1]='0.000'
        with self.assertRaisesRegex(ValueError,'differs'):assets.compare_tables(table,changed)

    def test_topology_comes_from_source_including_host_ports(self):
        links=assets.topology(ROOT/'experiment/topology.py')
        self.assertEqual(len(links),8)
        self.assertEqual(next(r for r in links if (r['a'],r['b'])==('s2','s4'))['capacity_mbps'],10)
        self.assertEqual(next(r for r in links if r['a']=='h3')['port_b'],2)

    def test_v2_source_byte_change_is_detected_before_calculation(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'data/v2').mkdir(parents=True)
            (root/'data/v2/manifest.json').write_text(json.dumps({'files':{'v2-batch.json':{'sha256':'0'*64}}}))
            (root/'data/v2/v2-batch.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'Pinned V2 input'):assets.load_v2(root)

    def test_tables_derive_cells_and_disclose_evidence_levels(self):
        _,data=assets.load_v2(ROOT)
        tables,ledger=assets.make_tables(ROOT,assets.read(ROOT/'results/tables/paper-evidence.json'),data['completed'],assets.read(ROOT/'results/matched/matched-report.json'))
        self.assertEqual(len(tables),6)
        self.assertEqual(ledger['parameters']['evidence_level'],'configuration')
        self.assertEqual(ledger['v2loss']['evidence_level'],'reported V2 summary')
        self.assertEqual(tables['v2loss']['rows'][4][-1],'0.587')
        altered=deepcopy(data['completed'])
        target=next(r for r in altered if (r['scenario'],r['bg_bps'],r['policy'])==('bursty',4_000_000,'ml'))
        target['udp_loss_percent']+=3
        new,_=assets.make_tables(ROOT,assets.read(ROOT/'results/tables/paper-evidence.json'),altered,assets.read(ROOT/'results/matched/matched-report.json'))
        self.assertNotEqual(new['v2loss']['rows'][4][-1],tables['v2loss']['rows'][4][-1])

if __name__=='__main__':unittest.main()
