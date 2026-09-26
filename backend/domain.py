"""Project-bound evidence and real runs. No model-generated engineering values."""
import hashlib
import re
import threading
import uuid
from pathlib import Path

from . import core
from .schema import (
    Evidence,
    EvidenceCreate,
    Project,
    ProjectCreate,
    Provenance,
    RunView,
)


def identifier(prefix):
    return prefix + "_" + uuid.uuid4().hex


class Domain:
    def __init__(self, store):
        self.store = store
        self.stop = threading.Event()
        self.worker = None

    def create_project(self, body: ProjectCreate):
        obj = Project(**body.model_dump(), project_id=identifier("project"), revision=1,
                      created_at=core.now(), updated_at=core.now()).model_dump(mode="json")
        return self.store.put("project", obj)

    def update_building(self, project_id, body):
        project = self.store.get("project", project_id)
        return self.store.put("project", {**project, "building": body.building.model_dump(), "updated_at": core.now()}, body.expected_revision)

    def add_file(self, project_id, filename, content):
        self.store.get("project", project_id)
        extension = Path(filename).suffix.lower()
        if extension not in {".idf", ".epw", ".pdf", ".csv", ".xlsx", ".xls", ".png", ".jpg", ".jpeg", ".ifc", ".json", ".xml"}:
            raise core.ValidationError("Unsupported file extension")
        if not content:
            raise core.ValidationError("Empty file")
        fid = identifier("file")
        path = self.store.root / "files" / (fid + extension)
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(content)
        return self.store.put("file", {"file_id": fid, "project_id": project_id,
                              "name": Path(filename.replace("\\", "/")).name,
                              "path": path.relative_to(self.store.root).as_posix(),
                              "hash": hashlib.sha256(content).hexdigest(), "size": len(content),
                              "timestamp": core.now()})

    def file_record(self, project_id, file_id):
        obj = self.store.get("file", file_id)
        if obj["project_id"] != project_id:
            raise core.ValidationError("Cross-project file binding rejected")
        path = core.relative_file(self.store.root, obj["path"])
        if core.sha(path) != obj["hash"]:
            raise core.ValidationError("Source file hash mismatch")
        return obj, path

    def add_evidence(self, project_id, body: EvidenceCreate):
        self.store.get("project", project_id)
        raw = body.model_dump(mode="json")
        if body.source_file:
            record, path = self.file_record(project_id, body.source_file)
            if body.type in {"idf", "epw"} and path.suffix != "." + body.type:
                raise core.ValidationError("Model/weather evidence has wrong file extension")
            digest = record["hash"]
        else:
            digest = core.hash_json(raw)
        obj = Evidence(**raw, evidence_id=identifier("evidence"), project_id=project_id,
                       revision=1, timestamp=core.now(), hash=digest).model_dump(mode="json")
        return self.store.put("evidence", obj)

    def review(self, project_id, evidence_id, body):
        obj = self.store.get("evidence", evidence_id)
        if obj["project_id"] != project_id:
            raise core.ValidationError("Cross-project evidence binding rejected")
        if body.review_state == "confirmed" and obj["status"] in {"MISSING", "AI_INFERRED"}:
            raise core.ValidationError("Missing/AI inferred evidence cannot be confirmed as a model input; register verified evidence separately")
        if obj["source_file"]:
            self.file_record(project_id, obj["source_file"])
        return self.store.put("evidence", {**obj, **body.model_dump(exclude={"expected_revision"}), "timestamp": core.now()}, body.expected_revision)

    def gate(self, project_id, scheme_id="baseline"):
        self.store.get("project", project_id)
        evidence = self.store.list("evidence", project_id)
        blockers, inputs = [], {}
        for kind in ["idf", "epw"]:
            candidates = [e for e in evidence if e["type"] == kind and e["review_state"] != "rejected" and (kind == "epw" or e["scheme_id"] == scheme_id)]
            if len(candidates) != 1:
                blockers.append({"code": "MISSING_INPUT" if not candidates else "CONFLICTING_INPUTS", "field": kind, "message": f"{kind.upper()} 需要唯一的有效证据；当前 {len(candidates)} 份", "action": "上传并登记资料；拒绝不适用版本，明确所用方案"})
                continue
            ev = candidates[0]
            inputs[kind] = ev
            if ev["review_state"] != "confirmed":
                blockers.append({"code": "REVIEW_REQUIRED", "field": kind, "message": ev["name"] + " 尚未人工确认项目/地点/范围/版本一致", "action": "复核原文件并写明确认依据"})
            try:
                _, path = self.file_record(project_id, ev["source_file"])
                if core.sha(path) != ev["hash"]:
                    raise core.ValidationError("Evidence/file hash mismatch")
                if kind == "idf":
                    text = re.sub(r"!.*", "", path.read_text(encoding="utf-8-sig", errors="replace"))
                    if not re.search(r"\bVersion\s*,\s*9\.0(?:\.\d+)?\s*;", text, re.IGNORECASE):
                        raise core.ValidationError("当前计算链仅验收 EnergyPlus 9.0 IDF，请使用匹配版本模型")
                    if not re.search(r"Output:SQLite\s*,\s*SimpleAndTabular\s*;", text, re.IGNORECASE):
                        raise core.ValidationError("IDF 需要 Output:SQLite,SimpleAndTabular; 和年度汇总输出")
                elif not path.read_text(encoding="utf-8-sig", errors="replace").startswith("LOCATION,"):
                    raise core.ValidationError("EPW LOCATION header missing")
            except (core.ValidationError, OSError, KeyError) as exc:
                blockers.append({"code": "INVALID_SOURCE", "field": kind, "message": str(exc), "action": "重新导入正确源文件并保留失败版本"})
        return {"project_id": project_id, "scheme_id": scheme_id, "can_simulate": not blockers,
                "can_recommend": False, "readiness": "READY_FOR_SIMULATION" if not blockers else "EVIDENCE_INSUFFICIENT",
                "blockers": blockers, "selected_evidence": inputs,
                "limitations": ["通过准入仅允许仿真，不证明模型代表真实建筑。", "结构化建筑字段是核对声明，当前不会自动修改 IDF。", "运行时继续核验 SQL、ERR、全年范围、面积和文件版本。", "费用、舒适性、校准及稳定性尚需独立证据，不能给出确定最优建议。"]}

    def submit(self, body):
        gate = self.gate(body.project_id, body.scheme_id)
        if not gate["can_simulate"]:
            raise core.ValidationError("Evidence gate rejected: " + "; ".join(b["message"] for b in gate["blockers"]))
        project = self.store.get("project", body.project_id)
        profile = core.get_profile(body.factor_profile_id)
        if profile["region"] not in {"*", project["building"]["region"]}:
            raise core.ValidationError("碳因子地区与项目不匹配")
        # Resolve engine before accepting a job; missing installation is not simulated success.
        engine = core.engine_path()
        selected = gate["selected_evidence"]
        model, _ = self.file_record(body.project_id, selected["idf"]["source_file"])
        weather, _ = self.file_record(body.project_id, selected["epw"]["source_file"])
        rid = identifier("run")
        case = {"case_id": body.project_id, "name": project["name"], "data_nature": project["data_nature"],
                "region": project["building"]["region"], "weather": weather["path"],
                "schemes": [{"scheme_id": body.scheme_id, "name": body.scheme_id, "model": model["path"], "cost": None}],
                "geometry_status": "not_reconstructed", "notes": gate["limitations"]}
        job = {**body.model_dump(), "run_id": rid, "case_id": body.project_id, "created_at": core.now(),
               "project_snapshot": project, "evidence_snapshot": selected, "case_snapshot": case,
               "factor_snapshot": profile, "code_hash": core.code_hash(), "engine_hash": core.sha(engine),
               "idd_hash": core.sha(engine.parent / "Energy+.idd"), "gate": gate}
        self.store.add_job(job)
        return self.view(rid)

    def stale_reasons(self, job):
        reasons = []
        if self.store.get("project", job["project_id"])["revision"] != job["project_snapshot"]["revision"]:
            reasons.append("建筑声明版本变化，需要重新核对模型")
        for ev in job["evidence_snapshot"].values():
            current = self.store.get("evidence", ev["evidence_id"])
            if current["revision"] != ev["revision"]:
                reasons.append("证据版本变化: " + ev["name"])
            try:
                self.file_record(job["project_id"], ev["source_file"])
            except (core.ValidationError, OSError, KeyError) as exc:
                reasons.append(str(exc))
        # Adding a conflicting model/weather also revokes readiness.
        gate = self.gate(job["project_id"], job["scheme_id"])
        if not gate["can_simulate"]:
            reasons.append("当前证据准入失效")
        if core.code_hash() != job["code_hash"]:
            reasons.append("计算代码版本变化")
        try:
            engine = core.engine_path()
            if core.sha(engine) != job["engine_hash"] or core.sha(engine.parent / "Energy+.idd") != job["idd_hash"]:
                reasons.append("计算引擎或 IDD 版本变化")
        except (core.ValidationError, OSError) as exc:
            reasons.append(str(exc))
        return reasons

    def execute(self, job):
        rid = job["run_id"]
        try:
            stale = self.stale_reasons(job)
            if stale:
                raise core.ValidationError("; ".join(stale))
            rd = self.store.root / "runs" / rid
            rd.mkdir(parents=True, exist_ok=False)
            # Stored before core invocation so it is part of the artifact manifest.
            core.write_json(rd / "request.json", {k: v for k, v in job.items() if k not in {"status", "error"}})
            result = core.run_simulation(job["case_id"], job["scheme_id"], job["factor_profile_id"], rd,
                                         case_override=job["case_snapshot"], profile_override=job["factor_snapshot"], file_root=self.store.root)
            if result["status"] == "failed":
                self.store.finish(rid, "failed", result["error"]["message"])
            elif abs(result["metrics"]["area_m2"] - job["project_snapshot"]["building"]["area_m2"]) > max(.1, result["metrics"]["area_m2"] * .001):
                self.store.finish(rid, "failed", "SQL area conflicts with building declaration; correct inputs and create a new run")
            else:
                self.store.finish(rid, "succeeded")
        except Exception as exc:
            self.store.finish(rid, "failed", str(exc))

    def start_worker(self):
        self.store.recover()
        def loop():
            while not self.stop.is_set():
                job = self.store.claim_job()
                if job:
                    self.execute(job)
                else:
                    self.stop.wait(.25)
        self.worker = threading.Thread(target=loop, daemon=True, name="vra-energyplus-worker")
        self.worker.start()

    def view(self, run_id):
        job = self.store.job(run_id)
        view = RunView(run_id=run_id, project_id=job["project_id"], case_id=job["case_id"], scheme_id=job["scheme_id"],
                       status=job["status"], data_nature=job["project_snapshot"]["data_nature"], created_at=job["created_at"], error=job["error"],
                       limitations=job["gate"]["limitations"]).model_dump(mode="json")
        rd = self.store.root / "runs" / run_id
        if job["status"] in {"queued", "running"}:
            return view
        try:
            result, manifest, _ = core.read_validated(rd, check_current=False)
            archived = core.read_json(rd / "request.json")
            expected = {k: v for k, v in job.items() if k not in {"status", "error"}}
            if archived != expected or result["case_id"] != job["case_id"] or result["scheme_id"] != job["scheme_id"]:
                raise core.ValidationError("Project/run request binding mismatch")
            fp = manifest["fingerprints"]
            if fp.get("model") != job["evidence_snapshot"]["idf"]["hash"] or fp.get("weather") != job["evidence_snapshot"]["epw"]["hash"]:
                raise core.ValidationError("Manifest/input evidence binding mismatch")
            expected_fingerprints = {"code": job["code_hash"], "engine": job["engine_hash"],
                                     "case": core.hash_json(job["case_snapshot"]), "factor": core.hash_json(job["factor_snapshot"])}
            if any(fp.get(key) != value for key, value in expected_fingerprints.items()) or manifest.get("engine_idd_hash") != job["idd_hash"]:
                raise core.ValidationError("Manifest/version snapshot binding mismatch")
            view.update(finished_at=result["finished_at"], engine_calls_executed=manifest["engine_calls_executed"], warnings_count=manifest.get("warnings"))
            if job["status"] == "succeeded":
                if result["status"] != "succeeded":
                    raise core.ValidationError("Worker/result state mismatch")
                view["provenance"] = Provenance(run_id=run_id, project_id=job["project_id"], case_id=job["case_id"], scheme_id=job["scheme_id"],
                    model_hash=fp["model"], weather_hash=fp["weather"], engine_version=manifest["engine_version"], code_version=fp["code"],
                    parser_version=core.PARSER_VERSION, factor_version=fp["factor"], timestamp=result["finished_at"]).model_dump()
                reasons = self.stale_reasons(job)
                view["stale_reasons"] = reasons
                if reasons:
                    view["status"] = "stale"
                else:
                    from .trust import Trust
                    view.update(metrics=result["metrics"], carbon=Trust(self).carbon_view(job, result["carbon"]))
        except (core.ValidationError, OSError, KeyError, ValueError) as exc:
            view.update(status="failed", metrics=None, carbon=None, error=job["error"] or str(exc))
        return view

    def claims(self, run_id, view=None):
        view = self.view(run_id) if view is None else view
        job = self.store.job(run_id)
        nodes = []
        for ev in job["evidence_snapshot"].values():
            evidence_state = "STALE"
            try:
                current = self.store.get("evidence", ev["evidence_id"])
                record, _ = self.file_record(ev["project_id"], ev["source_file"])
                if current["revision"] == ev["revision"] and current["review_state"] == "confirmed" and record["hash"] == ev["hash"]:
                    evidence_state = "ASSUMPTION" if ev["status"] == "ASSUMED" else "VALID"
            except (KeyError, OSError, core.ValidationError):
                evidence_state = "MISSING"
            nodes.append({"id": ev["evidence_id"] + ':v' + str(ev['revision']), "evidence_id": ev['evidence_id'], "kind": "Evidence", "label": ev["name"], "state": evidence_state,
                          "depends_on": [], "source_locator": ev["source_locator"], "revision": ev["revision"]})
        from .trust import Trust
        return Trust(self).graph(run_id, view, nodes)

    def report(self, run_id):
        view = self.view(run_id)
        job = self.store.job(run_id)
        state = {"failed": "SIMULATION_FAILED", "stale": "STALE"}.get(view["status"], "EVIDENCE_INSUFFICIENT")
        if (view.get("carbon") or {}).get("node_state") == "STALE":
            state = "PARTIALLY_STALE"
        report = {"schema_version": "vra.report.v1", "generated_at": core.now(), "project": job["project_snapshot"], "run": view,
                "evidence": list(job["evidence_snapshot"].values()), "claims": self.claims(run_id, view),
                "certificate": {"status": state, "current_recommendation": None, "candidate_schemes": [job["scheme_id"]],
                    "objective": "比较全年场地能耗，后续综合费用/舒适性/工程约束", "constraints": ["全年范围、面积、单位核验", "关键模型/天气证据人工确认"],
                    "evidence_status": view["status"], "stability_status": "NOT_ASSESSED", "conditions": ["当前模型、天气、工程输入与适用范围成立"],
                    "invalidation_conditions": ["输入/证据/引擎/代码/因子版本变化或文件损坏"], "counterexamples": None,
                    "unresolved_uncertainties": ["未做模型校准", "未开展反例搜索", "未完成费用和舒适性工程验收"],
                    "suggested_evidence_actions": ["复核定容 Warning 和未满足设定点时间", "补充账单/运行时段并验证模型适用性"],
                    "simulation_version": view["provenance"], "engineer_review": "UNSIGNED", "document_stage": "DRAFT_NOT_A_DECISION_APPROVAL"}}
        if hasattr(self, 'robustness') and job.get('project_id'):
            studies = [s for s in self.store.list('search', job['project_id']) if run_id in s['run_ids']]
            if studies:
                study = self.robustness.view(job['project_id'], studies[0]['search_id'])
                report['robustness'] = study
                report['certificate']['stability_status'] = study['stability_status']
                report['certificate']['counterexamples'] = [p for p in study['points'] if p['flipped']] if study['status'] == 'succeeded' else None
                report['certificate']['conditions'].append('仅限记录中的离散搜索点及预算；不代表连续域稳定或综合工程最优')
                report['certificate']['unresolved_uncertainties'] = ['未做模型校准', '搜索域外、未覆盖点和测量误差尚未排除', '未完成费用和舒适性工程验收']
                plans = [p for p in self.store.list('actionplan', job['project_id']) if p['search_id'] == study['search_id'] and p['search_revision'] == study['revision']]
                if plans and study['status'] == 'succeeded':
                    report['evidence_action_plan'] = plans[0]
                    report['certificate']['suggested_evidence_actions'] += [a['method'] + '；费用情景 CNY ' + str(a['cost_cny']) + '；可排除已观察反例 ' + str(a['excluded_observed_counterexamples']) + '（条件假设，非保证收益）' for a in plans[0]['actions']]
        return report

    def project_claims(self, project_id):
        latest = {}
        for job in self.store.jobs(project_id):
            latest.setdefault(job['scheme_id'], job['run_id'])
        graphs = [self.claims(rid) for rid in latest.values()]
        nodes = {n['id']: n for graph in graphs for n in graph['nodes']}
        energy = [rid + ':energy' for rid in latest.values()]
        carbon = [rid + ':carbon' for rid in latest.values()]
        for suffix, label, deps in [('energy-ranking', '能耗排序', energy), ('carbon-ranking', '运行碳排序', carbon)]:
            statuses = {nodes[d]['state'] for d in deps}
            status = 'STALE' if 'STALE' in statuses else 'VALID' if len(deps) >= 2 and statuses == {'VALID'} and 'baseline' in latest else 'UNKNOWN'
            if suffix == 'carbon-ranking' and len({(self.view(r).get('carbon') or {}).get('profile_hash') for r in latest.values()}) != 1:
                status = 'UNKNOWN'
            nodes[project_id + ':' + suffix] = {'id': project_id + ':' + suffix, 'kind': 'Comparison', 'label': label, 'state': status, 'depends_on': deps}
        return {'project_id': project_id, 'nodes': list(nodes.values()), 'selected_runs': latest}

    def compare(self, run_ids):
        views = [self.view(rid) for rid in run_ids]
        if any(v["status"] != "succeeded" for v in views):
            raise core.ValidationError("Failed/stale/incomplete runs cannot be compared")
        if len({v["project_id"] for v in views}) != 1 or len({v["scheme_id"] for v in views}) != len(views):
            raise core.ValidationError("Comparison requires unique schemes from one project")
        bases = [v for v in views if v["scheme_id"] == "baseline"]
        if len(bases) != 1:
            raise core.ValidationError("Exactly one baseline required")
        for key in ["weather_hash", "engine_version", "code_version"]:
            if len({v["provenance"][key] for v in views}) != 1:
                raise core.ValidationError("Comparison context differs: " + key)
        base = bases[0]
        for view in views:
            if abs(view["metrics"]["area_m2"] - base["metrics"]["area_m2"]) > .1:
                raise core.ValidationError("Comparison areas differ")
            energy = base["metrics"]["annual_energy_kwh"]
            view["saving_rate_pct"] = (1 - view["metrics"]["annual_energy_kwh"] / energy) * 100 if energy else None
            a, b = base["carbon"]["operating_carbon_kg"], view["carbon"]["operating_carbon_kg"]
            same_factors = base['carbon'].get('profile_hash') == view['carbon'].get('profile_hash')
            view["engineering_reduction_kg"] = a - b if a is not None and b is not None and same_factors else None
        return {"results": views, "energy_order": [v["scheme_id"] for v in sorted(views, key=lambda x: x["metrics"]["annual_energy_kwh"])],
                "recommendation": None, "decision_status": "EVIDENCE_INSUFFICIENT", "note": "仅能耗排序。未评估反例、成本、校准和工程约束，不代表综合最优或可签发碳信用。"}

    def create_reference(self):
        case = core.load_case("reference_5zone")
        project = self.create_project(ProjectCreate(name="官方五区参考项目 · 非实测", data_nature="engineering_reference", building={"use": "办公参考模型", "location": "Golden, Colorado", "region": "US-CO", "area_m2": 927.2, "floors": 1, "notes": "官方 5ZoneAirCooled 派生；追加保温为教学假设；无真实建筑校准。"}))
        paths = [("epw", None, core.relative_file(core.ROOT, case["weather"]))]
        paths += [("idf", s["scheme_id"], core.relative_file(core.ROOT, s["model"])) for s in case["schemes"]]
        for kind, scheme, path in paths:
            file = self.add_file(project["project_id"], path.name, path.read_bytes())
            self.add_evidence(project["project_id"], EvidenceCreate(type=kind, name=path.name, scheme_id=scheme, source_file=file["file_id"],
                source_locator="EnergyPlus 9.0.1 ExampleFiles / Golden-NREL weather; complete file",
                authority="EnergyPlus distributed reference input; derivative insulation is assumed",
                permission="EnergyPlus license retained in third_party_notices and fixtures/demo/reference_5zone",
                acquisition_method="explicit_reference_import", responsible_person="待工程师确认", status="IMPORTED", uncertainty="非实测模型；不代表当地真实项目"))
        return project
