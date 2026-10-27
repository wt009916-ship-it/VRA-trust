"""Versioned building workbench and persistent LangGraph recognition/review workflow."""
import threading
from typing import TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from . import core, model_export, model_import, model_geometry
from .domain import identifier
from .model_schema import ImportOptions, ModelDraft
from .schema import BuildingUpdate, EvidenceCreate, EvidenceReview


class ImportState(TypedDict, total=False):
    workflow_id: str
    project_id: str
    options: dict
    candidate: dict
    reviewed_model: dict
    result: dict


class Modeling:
    def __init__(self, domain, gateway):
        self.domain, self.store, self.gateway = domain, domain.store, gateway
        self.lock = threading.RLock()
        self.capacity = threading.BoundedSemaphore(2)
        self.checkpoints = self.store.root / "model-workflows.sqlite3"

    def get(self, project_id):
        self.store.get("project", project_id)
        models = self.store.list("model", project_id)
        return models[0] if models else None

    def save(self, project_id, body, actor, source=None, workflow_id=None):
        with self.lock:
            for equipment in body.equipment:
                record, _ = self.domain.file_record(project_id, equipment.source_file_id)
                if record['hash'] != equipment.source_file_hash:
                    raise core.ValidationError('设备清单原件哈希发生变化，须重新导入和复核')
            old = self.get(project_id)
            if old and workflow_id:
                for version in self.store.history("model", old["model_id"]):
                    if version.get("workflow_id") == workflow_id:
                        if version.get("review_hash") != core.hash_json(body.model_dump()):
                            raise core.ValidationError("此导入任务已经保存了另一份复核结果")
                        return version
            if body.expected_revision != (old["revision"] if old else 0):
                raise core.ValidationError("模型版本冲突，请刷新后再编辑")
            sources = source if source is not None else (old or {}).get("sources", [])
            sources = list(sources)
            known = {s['file_id'] for s in sources}
            for equipment in body.equipment:
                if equipment.source_file_id not in known:
                    record, _ = self.domain.file_record(project_id, equipment.source_file_id)
                    sources.append({k: record[k] for k in ('file_id', 'hash', 'name')})
                    known.add(equipment.source_file_id)
            for ref in sources:
                record, _ = self.domain.file_record(project_id, ref["file_id"])
                if record["hash"] != ref["hash"]:
                    raise core.ValidationError("模型来源文件已变化")
            data = body.model_dump(exclude={"expected_revision"})
            data.update(model_id=old["model_id"] if old else identifier("model"), project_id=project_id,
                        sources=sources, actor=actor, updated_at=core.now(),
                        workflow_id=workflow_id, review_hash=core.hash_json(body.model_dump()),
                        area_m2=sum(model_geometry.floor_area(r.model_dump()) for r in body.rooms
                                    if r.include_floor_area is not False),
                        status="REVIEWED" if body.reviewed else "DRAFT")
            return self.store.put("model", data, body.expected_revision)

    def history(self, project_id):
        current = self.get(project_id)
        return self.store.history("model", current["model_id"]) if current else []

    def _graph(self, saver, actor):
        def recognize(state):
            options = ImportOptions.model_validate(state["options"])
            record, path = self.domain.file_record(state["project_id"], options.file_id)
            candidate = model_import.extract(path, options, self.gateway)
            candidate["source"] = {"file_id": record["file_id"], "hash": record["hash"], "name": record["name"]}
            return {"candidate": candidate}

        def review(state):
            reviewed = interrupt({"action": "review_rooms", "candidate": state["candidate"]})
            body = ModelDraft.model_validate(reviewed)
            if not body.reviewed:
                raise core.ValidationError("恢复工作流前须确认空间几何；参数仍可作为明确假设")
            return {"reviewed_model": body.model_dump()}

        def commit(state):
            current = self.get(state["project_id"])
            sources = {s["file_id"]: s for s in (current or {}).get("sources", [])}
            source = state["candidate"]["source"]
            if state['candidate'].get('diagnostics', {}).get('method') == 'IFC_ELEMENT_SECTION':
                source = {**source, 'reconstruction_coverage': state['candidate']['diagnostics']}
            sources[source["file_id"]] = source
            result = self.save(state["project_id"], ModelDraft.model_validate(state["reviewed_model"]), actor,
                               list(sources.values()), state["workflow_id"])
            return {"result": result}

        graph = StateGraph(ImportState)
        graph.add_node("recognize", recognize)
        graph.add_node("engineer_review", review)
        graph.add_node("save_model", commit)
        graph.add_edge(START, "recognize")
        graph.add_edge("recognize", "engineer_review")
        graph.add_edge("engineer_review", "save_model")
        graph.add_edge("save_model", END)
        return graph.compile(checkpointer=saver)

    def start_import(self, project_id, options, actor):
        source, _ = self.domain.file_record(project_id, options.file_id)
        if not self.capacity.acquire(blocking=False):
            raise core.ValidationError("识别工作线程已满，请稍后再试")
        record = self.store.put("import", {"import_id": identifier("import"), "project_id": project_id,
                                "status": "running", "created_at": core.now(), "options": options.model_dump(),
                                "actor": actor, "error": None,
                                "source": {k: source[k] for k in ("file_id", "name", "hash", "size")}})
        try:
            with SqliteSaver.from_conn_string(str(self.checkpoints)) as saver:
                graph = self._graph(saver, actor)
                output = graph.invoke({"workflow_id": record["import_id"], "project_id": project_id, "options": options.model_dump()},
                                      {"configurable": {"thread_id": record["import_id"]}})
            return self.store.put("import", {**record, "status": "awaiting_review",
                                            "candidate": output["candidate"]}, record["revision"])
        except Exception as exc:
            self.store.put("import", {**record, "status": "failed", "error": str(exc),
                           "diagnostics": getattr(exc, "diagnostics", None)}, record["revision"])
            raise
        finally:
            self.capacity.release()

    def resume(self, project_id, import_id, body, actor):
        with self.lock:
            record = self.store.get("import", import_id)
            if record["project_id"] != project_id:
                raise KeyError(import_id)
            if record["status"] == "completed":
                # A retried browser request must not append a second model revision.
                return record
            if record["status"] != "awaiting_review":
                raise core.ValidationError("任务不在待复核状态")
            if not body.reviewed:
                raise core.ValidationError("请核对并确认空间几何")
            current = self.get(project_id)
            already_saved = current and any(m.get("workflow_id") == import_id for m in self.store.history("model", current["model_id"]))
            if not already_saved and body.expected_revision != (current["revision"] if current else 0):
                raise core.ValidationError("模型已修改，请刷新并合并房间后重试")
            with SqliteSaver.from_conn_string(str(self.checkpoints)) as saver:
                graph = self._graph(saver, actor)
                output = graph.invoke(Command(resume=body.model_dump()), {"configurable": {"thread_id": import_id}})
            return self.store.put("import", {**record, "status": "completed",
                                            "model": output["result"], "reviewed_at": core.now()}, record["revision"])

    def recover(self):
        # Interrupted external recognition needs explicit retry; review checkpoints survive restart.
        for record in self.store.list("import"):
            if record["status"] == "running":
                self.store.put("import", {**record, "status": "failed",
                    "error": "识别进程中断，请重试；已完成的复核检查点保留"}, record["revision"])

    def validate(self, project_id):
        model = self.get(project_id)
        blockers = []
        if not model:
            return {"can_publish": False, "blockers": ["尚未建立空间模型"], "limitations": model_export.LIMITATIONS}
        if not model["reviewed"]:
            blockers.append("空间几何尚未复核")
        if not model["thermal"]:
            blockers.append("热工参数不完整")
        for source in model['sources']:
            coverage = source.get('reconstruction_coverage') or {}
            missing = {s['storey'] for s in coverage.get('storeys', [])
                       if s['status'] != 'candidate' or s.get('excluded_subminimum_area_m2', 0) > .01}
            unresolved_scope = missing - model.get('scope_exclusions', {}).keys()
            if unresolved_scope:
                blockers.append('构件重建尚有未恢复区域或小型空间，须明确楼层范围处置（保留为排除范围，不能算完整覆盖）：'+', '.join(sorted(unresolved_scope)))
        unresolved = [r["name"] for r in model["rooms"]
                      if r.get("conditioned", True) is None or r.get("include_floor_area", True) is None]
        if unresolved:
            blockers.append("须确认空调及计入面积属性：" + "、".join(unresolved)[:1000])
        if model["area_m2"] <= 0:
            blockers.append("至少一个空间须计入项目面积")
        geometric_area = sum(model_geometry.floor_area(r) for r in model['rooms'] if r.get('include_floor_area') is not False)
        if abs(geometric_area-model['area_m2']) > max(.0001, geometric_area*1e-6):
            blockers.append(f'几何楼面投影口径已更新，请重新保存复核版本：旧面积{model["area_m2"]:.4f}、当前{geometric_area:.4f}m²；未改写旧版本')
        geometry_review = None
        try:
            surfaces, numerical = model_export.geometry(model, return_report=True)
            _, adjustment = model_geometry.thermal_geometry_model(model)
            independent = model_export.geometry_audit(model)
            if not independent["passed"]:
                prefix = 'EnergyPlus 几何预检失败：' if not independent.get('engine_compatibility', {}).get('passed', True) else 'Honeybee 校验失败：'
                blockers.append(prefix + "; ".join(i["message"] for i in independent["issues"])[:1500])
            geometry_review = {
                "independent_audit": independent, "numerical_precision": numerical,
                "coverage": {
                    "thermal_mass_assemblies": list((model.get("thermal") or {}).get("constructions", {})),
                    "hourly_operation": bool((model.get("thermal") or {}).get("operation")),
                    "actual_hvac_equipment": bool(model.get('equipment')),
                    'hvac_scope': model_export.scope(model),
                    "nameplate_equipment_count": len(model.get('equipment', [])),
                    "source_window_geometry": (model.get('thermal') or {}).get('window_geometry') == 'source',
                    'column_mass_reduction': numerical.get('column_mass_reduction', []),
                    "inferred_rooms": sum(bool(r.get("drawing") or r.get("reconstruction") or r.get('geometry_inferred')) for r in model["rooms"]),
                    "adiabatic_area_m2": sum(model_geometry.frame(s["points"])["poly"].area for s in surfaces if s["boundary"] == "Adiabatic"),
                },
                "assumed_gap_faces": sum("ASSUMED: facing" in s["boundary_basis"] for s in surfaces),
                "boundary_faces": {kind: sum(s["boundary"] == kind for s in surfaces)
                                   for kind in ("Surface", "Outdoors", "Ground", "Adiabatic")},
                "adjustment": adjustment,
            }
            for source in model["sources"]:
                self.domain.file_record(project_id, source["file_id"])
        except core.ValidationError as exc:
            blockers.append(str(exc))
        declared = self.store.get("project", project_id)["building"]["area_m2"]
        if abs(declared-model["area_m2"]) > max(.1, model["area_m2"]*.001):
            blockers.append(f"模型面积 {model['area_m2']:.2f} m² 与项目声明 {declared:.2f} m² 不符；请先同步声明")
        return {"can_publish": not blockers, "blockers": blockers, "model_revision": model["revision"],
                "area_m2": model["area_m2"], "limitations": model_export.LIMITATIONS,
                "geometry_review": geometry_review}

    def publish(self, project_id, body):
        with self.lock:
            model = self.get(project_id)
            if not model or model["revision"] != body.revision:
                raise core.ValidationError("模型版本变化，请刷新")
            check = self.validate(project_id)
            if not check["can_publish"]:
                raise core.ValidationError("；".join(check["blockers"]))
            text, surfaces = model_export.idf(model)
            _, adjustment = model_geometry.thermal_geometry_model(model)
            binding = {"model_id": model["model_id"], "revision": model["revision"],
                       "model_hash": core.hash_json(model),
                       "compiler": model_export.COMPILER_VERSION, "compiler_hash": model_export.compiler_hash(),
                       "boundary_summary": {kind: sum(s["boundary"] == kind for s in surfaces)
                                            for kind in ("Surface", "Outdoors", "Ground", "Adiabatic")},
                       "ifc_unpaired_policy": model["thermal"].get("ifc_unpaired_policy", "reject"),
                       "geometry_adjustment": adjustment,
                       "independent_audit": check["geometry_review"]["independent_audit"],
                       "numerical_precision": check["geometry_review"]["numerical_precision"],
                       "scope": model_export.scope(model), 'scope_exclusions': model.get('scope_exclusions', {}),
                       'equipment': [{'zone_id': e['zone_id'], 'manufacturer': e['manufacturer'], 'model': e['model'],
                                      'source_file_id': e['source_file_id'], 'source_file_hash': e['source_file_hash'],
                                      'curve_basis': e['curve_basis']} for e in model.get('equipment', [])],
                       "limitations": model_export.LIMITATIONS}
            existing = [ev for ev in self.store.list("evidence", project_id)
                        if ev["type"] == "idf" and ev["scheme_id"] == body.scheme_id and ev["review_state"] != "rejected"]
            if len(existing) == 1 and existing[0].get("value") == binding and existing[0]["review_state"] == "confirmed":
                return {"evidence": existing[0], "binding": binding, "reused": True}
            file = self.domain.add_file(project_id, f"model-v{model['revision']}-{body.scheme_id}.idf", text.encode())
            evidence = self.domain.add_evidence(project_id, EvidenceCreate(
                type="idf", name=f"空间模型 v{model['revision']} · {'PTHP耗电' if model_export.scope(model) == 'packaged_heat_pump_electricity' else '理想冷热需求'} · {body.scheme_id}",
                source_file=file["file_id"], scheme_id=body.scheme_id, source_locator="VRA Building Model "+model["model_id"],
                value=binding, authority=body.responsible_person, permission="项目内部工程分析",
                acquisition_method="确定性空间实体与热边界编译器", responsible_person=body.responsible_person,
                status="ASSUMED" if model["thermal"]["basis"] == "assumed_scenario" else "DOCUMENTED",
                uncertainty="；".join(model_export.LIMITATIONS)))
            evidence = self.domain.review(project_id, evidence["evidence_id"], EvidenceReview(
                expected_revision=evidence["revision"], review_state="confirmed",
                responsible_person=body.responsible_person, review_note=body.review_note))
            for ev in existing:
                self.domain.review(project_id, ev["evidence_id"], EvidenceReview(
                    expected_revision=ev["revision"], review_state="rejected",
                    responsible_person=body.responsible_person,
                    review_note="由已复核建筑模型重新生成并替代；保留旧证据历史。"))
            return {"evidence": evidence, "binding": binding, "surfaces": len(surfaces), "reused": False}

    def sync_area(self, project_id, revision):
        with self.lock:
            model = self.get(project_id)
            if not model or model["revision"] != revision:
                raise core.ValidationError("模型版本变化，请刷新")
            project = self.store.get("project", project_id)
            if abs(project["building"]["area_m2"]-model["area_m2"]) < .000001:
                return project
            return self.domain.update_building(project_id, BuildingUpdate(expected_revision=project["revision"],
                building={**project["building"], "area_m2": model["area_m2"]}))
