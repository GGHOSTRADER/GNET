"""Resume bounded synthetic broker acceptance with durable original job IDs."""
import argparse
import json
from pathlib import Path
import subprocess
import time
from datetime import datetime, timezone
from uuid import uuid4

BASE = Path(__file__).resolve().parents[1]
ARTIFACTS = BASE / '.artifacts'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=['discover', 'development', 'final'], required=True)
    parser.add_argument('--fixture', choices=['generic', 'full'], default='full')
    args = parser.parse_args()
    config_path = ARTIFACTS / 'client-delivery-installed/client-config.json'
    config = json.loads(config_path.read_text(encoding='utf-8-sig'))
    if config['client_release_id'] != 'gnet-client-v63-browser-regressions-r2' or config['broker_release_id'] != 'guarded-v42-recorded-review-fix':
        raise RuntimeError('Exact installed V63 client / V42 broker required')
    full = args.fixture == 'full'
    receipt_path = ARTIFACTS / ('v63-installed-synthetic-workflow-full.json' if full else 'v63-installed-synthetic-workflow.json')
    seed = json.loads((ARTIFACTS / ('fresh-delivery-fixture.json' if full else 'v39-generic-primary-acceptance.json')).read_text())
    expected_export = 'acceptance-client-delivery-oct09-fresh-r1' if full else 'acceptance-generic-primary-v39-r1'
    if not seed['synthetic_only'] or seed['real_data_used'] or seed['export_id'] != expected_export:
        raise RuntimeError('Exact previously reviewed fabricated fixture required')
    prefix = 'delivery-acceptance-' if full else 'v39-generic-'
    source_payload = json.loads((ARTIFACTS / (prefix + 'prepare_ts_primary_source.request.json')).read_text())['payload']
    intake_payload = json.loads((ARTIFACTS / (prefix + 'ingest_ts_export.request.json')).read_text())['payload']
    state = json.loads(receipt_path.read_text()) if receipt_path.exists() else {
        'client_release_id': config['client_release_id'], 'release_id': config['broker_release_id'],
        'synthetic_only': True, 'real_data_used': False, 'isolation_certified': False,
        'export_id': seed['export_id'], 'jobs': [], 'development_passed': False,
        'final_evaluation_run': False,
    }
    if state['release_id'] != config['broker_release_id'] or state['export_id'] != seed['export_id']:
        raise RuntimeError('Saved acceptance scope differs')
    command = [config['python'], '-B', '-I', str(Path(config['package_root']) / 'client_entry.py'), '--config', str(config_path)]

    def save():
        receipt_path.write_text(json.dumps(state, indent=2), encoding='utf-8')

    def cli(*arguments):
        result = subprocess.run(command + list(arguments), capture_output=True, text=True, encoding='utf-8', timeout=30)
        if result.returncode:
            raise RuntimeError((result.stdout + result.stderr)[:1000])
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise RuntimeError('Client returned no valid JSON; retain original jobs') from error

    def job(operation, payload, *, label=None, expected_error=None):
        label = label or operation
        previous = [j for j in state['jobs'] if j.get('label', j['operation']) == label]
        if previous:
            item = previous[-1]
            if item['payload'] != payload:
                raise RuntimeError('Saved request payload differs: ' + operation)
        else:
            identifier = 'job-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid4().hex
            item = {'operation': operation, 'label': label, 'payload': payload, 'job_id': identifier, 'submitted': False, 'expected_error': expected_error}
            state['jobs'].append(item)
            save()
        if not item['submitted']:
            path = ARTIFACTS / ('v63-synthetic-' + args.fixture + '-' + label + '.request.json')
            path.write_text(json.dumps({'schema_version': '1.0', 'job_id': item['job_id'], 'operation': operation,
                'payload': payload, 'release_id': config['broker_release_id'],
                'limits': {'workers': 1, 'wall_seconds': 180, 'memory_mb': 2048},
                'output_level': 'reports_and_metrics'}), encoding='utf-8')
            submitted = cli('submit', '--request', str(path))
            item['submitted'] = True
            save()
            if submitted.get('trigger_status') == 'failed':
                raise RuntimeError('Task trigger failed; retain original job ' + item['job_id'])
        print(json.dumps({'operation': operation, 'job_id': item['job_id']}), flush=True)
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            status = cli('status', '--job-id', item['job_id'])
            if status['state'] in ['published', 'failed', 'cancelled']:
                report = cli('report', '--job-id', item['job_id'])
                item.update(state=status['state'], usable=report['usable'], artifact_ids=report['artifact_ids'],
                    counts=report['counts'], reports=report['reports'], error=report.get('error'))
                save()
                if expected_error:
                    if report['usable'] or (report.get('error') or {}).get('code') != expected_error:
                        raise RuntimeError('Expected rejection did not match: ' + expected_error)
                    print(json.dumps({'operation': operation, 'expected_rejection_passed': expected_error}), flush=True)
                    return report
                if status['state'] != 'published' or report.get('error'):
                    raise RuntimeError(str(report.get('error'))[:900])
                if not report['usable'] and operation != 'capabilities':
                    raise RuntimeError('Broker returned unusable output: ' + operation)
                print(json.dumps({'operation': operation, 'passed': True, 'counts': report['counts']}), flush=True)
                return report
            time.sleep(1)
        raise RuntimeError('Bounded wait ended; resume original job ' + item['job_id'])

    try:
        state['failure'] = None
        state['health'] = cli('health')
        if args.stage == 'discover':
            job('capabilities', {})
            catalog = job('data_catalog', {'matching_ids': [source_payload['dataset_id']], 'page_size': 1, 'only_enabled': False})
            state['catalog'] = catalog['metrics']['catalog']
            review = job('ts_review_status', {'review_id': intake_payload['policy_id']})
            state['review'] = review['metrics']['review']
            template = job('ts_review_template', {'export_id': seed['export_id'], 'automatic_checks': True, 'synthetic': True})
            state['development_end'] = template['metrics']['review_template']['primary_review']['source_contract']['development_end']
            state['discovery_passed'] = True
        elif args.stage == 'development':
            if not state.get('discovery_passed') or not state['review']['policy_active']:
                raise RuntimeError('Exact active synthetic policy discovery must pass first')
            job('ingest_ts_export', intake_payload)
            source = job('prepare_ts_primary_source', source_payload)['artifact_ids'][0]
            labels = job('build_primary_labels', {'source_artifact_id': source})['artifact_ids'][0]
            data = job('build_training_dataset', {'input_mode': 'tradestation', 'source_artifact_id': source, 'primary_labels_artifact_id': labels})['artifact_ids'][0]
            end = state['development_end']
            analysis = job('analyze_features', {'training_dataset_id': data, 'input_mode': 'tradestation', 'development_end': end, 'n_splits': 2, 'embargo_pct': .01})
            facts = analysis['metrics']['feature_analysis']
            names = [name for name in facts['names'] if name not in facts['constant_features']]
            if not names:
                raise RuntimeError('Synthetic feature pool contains no variable features')
            review = job('review_features', {'analysis_artifact_id': analysis['artifact_ids'][0], 'training_dataset_id': data, 'decision': 'pass', 'feature_names': names, 'reason': 'Synthetic installed V63 acceptance; retain variable training-prefix features. No predictive claim.'})['artifact_ids'][0]
            model = job('train_model', {'training_dataset_id': data, 'input_mode': 'tradestation', 'development_end': end, 'model_family': 'xgboost', 'feature_names': names, 'feature_review_id': review, 'n_splits': 2, 'embargo_pct': .01, 'seed': 42, 'xgboost': {'rounds': 8, 'max_depth': 2, 'learning_rate': .1}})['artifact_ids'][0]
            scores = job('score_model', {'model_artifact_id': model, 'training_dataset_id': data, 'mode': 'walk_forward', 'development_end': end, 'threshold': .5})['artifact_ids'][0]
            replay = job('ml_gated_replay', {'predictions_artifact_id': scores, 'replay_mode': 'native_executed_positions'})
            if replay['metrics'].get('counterfactual_ts_engine_run'):
                raise RuntimeError('Unexpected native replay interpretation')
            state.update(development_passed=True, selected_features=names, model_artifact_id=model, predictions_artifact_id=scores, replay_counts=replay['counts'])
        else:
            if not full or not state['development_passed']:
                raise RuntimeError('Matching full synthetic development acceptance must pass first')
            final = json.loads((ARTIFACTS / 'v63-native-final-seed.json').read_text())
            if not final['synthetic_only'] or final['real_data_used'] or not final['review_activated'] or final.get('failure') or final['release_id'] != config['broker_release_id']:
                raise RuntimeError('Exact fresh synthetic final archive needs local Administrator review')
            dataset = final['dataset_id']
            policy = final['document']['policy']
            coverage = policy['manifest']['coverage']
            job('ingest_ts_export', {'export_id': final['export_id'], 'policy_id': policy['policy_id']}, label='final-ingest')
            experiment = 'browser-v63-native-final-r1'
            job('reserve_experiment', {'experiment_id': experiment, 'dataset_id': dataset,
                'holdout_start': coverage['first_event'], 'holdout_end': coverage['last_event']})
            frozen = job('freeze_experiment', {'experiment_id': experiment, 'model_artifact_id': state['model_artifact_id'],
                'predictions_artifact_id': state['predictions_artifact_id'], 'final_primary_review_id': final['document']['primary_review']['review_id']})
            payload = {'experiment_id': experiment, 'freeze_hash': frozen['metrics']['experiment']['freeze_hash']}
            evaluated = job('evaluate_final', payload)
            result_id = evaluated['artifact_ids'][0]
            job('statistics_report', {'result_artifact_id': result_id})
            job('evaluate_final', payload, label='final-repeat-rejection', expected_error='final_evaluation_consumed')
            state.update(final_evaluation_run=True, final_passed=True, experiment_id=experiment, final_result_id=result_id)
        save()
        print(json.dumps({'stage': args.stage, 'passed': True, 'receipt': str(receipt_path)}), flush=True)
        return 0
    except Exception as error:
        state['failure'] = str(error)[:1200]
        save()
        print(json.dumps({'passed': False, 'failure': state['failure'], 'receipt': str(receipt_path)}), flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
