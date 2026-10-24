"""Author-independent terrain identity followed by the chosen route's own pose.

Never transfer coordinates between atlases. The second stage verifies the
selected original against the current screenshot before it may be displayed.
"""
from .live import presentation_candidate,cached_alignment_candidate
from .matcher import MatchResult

class TerrainIdentityMatcher:
    """Compare both reference drawings, collapsing only explicit terrain aliases.

    Its poses are identity evidence only and must never be rendered. The
    selected author's independent alignment supplies every display coordinate.
    """
    def __init__(self,index,matcher_type):
        from pathlib import Path
        index=Path(index)/'recognition' if (Path(index)/'recognition/index.json').exists() else index
        self.duo=matcher_type(index,difficulty='nightmare',mode='duo')
        self.solo=matcher_type(index,difficulty='nightmare',mode='solo')
        self.floor_hint=None
        self.by_terrain={r.terrain_id:r.map_id for r in self.solo.references if r.terrain_id}
    @property
    def references(self):return self.solo.references
    def match(self,pixels):
        from dataclasses import replace
        accepted=[];details=[];ambiguous=set()
        for matcher in (self.duo,self.solo):
            matcher.floor_hint=self.floor_hint
            result=matcher.match(pixels);details.append(result.to_dict())
            candidate=presentation_candidate(result)[0]
            if candidate is None:
                # Retain strong but tied phone hypotheses for independent route
                # verification. These are identities only, never render poses.
                if result.reason=='mobile_identity_ambiguous':
                    hypotheses=result.diagnostics.get('rejected_candidates',[])
                    top=max((h.get('explained') or 0 for h in hypotheses),default=0)
                    for h in hypotheses:
                        if (h.get('explained') or 0)<max(.65,top-.04) or h.get('contradiction',1)>.25 or h.get('retrieval_score',0)<4:continue
                        if self.floor_hint is not None and h.get('floor')!=self.floor_hint:continue
                        ref=next((r for r in matcher.references if r.map_id==h['map_id']),None)
                        if ref is None:continue
                        canonical=ref.map_id if matcher is self.solo else self.by_terrain.get(ref.terrain_id)
                        if canonical is not None:ambiguous.add((canonical,h['floor']))
                continue
            ref=next(r for r in matcher.references if r.map_id==candidate.map_id)
            # A solo reference is already the canonical recognition identity.
            # Only alternate duo drawings require an explicit terrain alias.
            map_id=ref.map_id if matcher is self.solo else self.by_terrain.get(ref.terrain_id)
            if map_id is not None:accepted.append(replace(candidate,map_id=map_id,mode='solo'))
        # Scores from different atlas drawings/views are not calibrated against
        # one another. Conflicting accepted identities require more evidence;
        # a slightly higher boundary score must never pick the other map.
        identities={(c.map_id,c.floor) for c in accepted}
        if not accepted and len(ambiguous)>=2:
            return MatchResult(reason='ambiguous_reference_drawings',diagnostics=dict(identity_only=True,
                reference_drawings=details,identity_hypotheses=[dict(map_id=m,floor=f) for m,f in sorted(ambiguous)]))
        if len(identities)!=1:
            return MatchResult(reason='conflicting_reference_drawings' if accepted else 'terrain_identity_unconfirmed',
                diagnostics=dict(identity_only=True,reference_drawings=details,
                    identity_hypotheses=[dict(map_id=c.map_id,floor=c.floor) for c in accepted]))
        chosen=max(accepted,key=lambda c:c.explained or 0)
        return MatchResult(candidates=[chosen],diagnostics=dict(identity_only=True,
            render_coordinates_invalid=True,reference_drawings=details))

def terrain_recognizer(index,matcher_type):
    return TerrainIdentityMatcher(index,matcher_type)


class AuthorRouteMatcher:
    def __init__(self,primary,recognizer):
        self.primary=primary
        self.recognizer=recognizer
        self.floor_hint=None
    @property
    def references(self):return self.primary.references
    def register_known(self,pixels,map_id):
        self.primary.floor_hint=self.floor_hint
        return self.primary.register_known(pixels,map_id)
    def register_manual_floor(self,pixels,map_id,floor):
        return self.primary.register_manual_floor(pixels,map_id,floor)
    def standalone(self,pixels):
        if not any(not r.recognition_map_id for r in self.primary.references):return None
        self.primary.floor_hint=self.floor_hint
        result=self.primary.match(pixels)
        candidate=presentation_candidate(result)[0]
        if candidate is not None and any(r.map_id==candidate.map_id and not r.recognition_map_id for r in self.primary.references):return result
        return None
    def resolve_conflict(self,pixels,identity):
        """Only a clear independent fit in the selected author's atlas can arbitrate."""
        hypotheses={(h['map_id'],h['floor']) for h in identity.diagnostics.get('identity_hypotheses',[])}
        aligned=[]
        for map_id,floor in hypotheses:
            self.primary.floor_hint=floor
            group=[]
            for ref in self.primary.references:
                if ref.recognition_map_id!=map_id:continue
                result=self.primary.register_known(pixels,ref.map_id)
                candidate=cached_alignment_candidate(result)[0]
                if candidate is not None and candidate.floor==floor:group.append((candidate,result))
            if group:aligned.append(max(group,key=lambda x:x[0].explained))
        aligned.sort(key=lambda x:-(x[0].explained or 0))
        if len(aligned)!=len(hypotheses) or len(aligned)<2:return None
        candidate,result=aligned[0];margin=candidate.explained-aligned[1][0].explained
        if candidate.explained<.65 or candidate.contradiction>.25 or candidate.retrieval_score<4 or margin<.04:return None
        if hasattr(self.primary,'ensure'):self.primary.ensure(candidate.map_id)
        result.candidates=[candidate]
        result.diagnostics['author_conflict_recovered']=dict(margin=margin,independent_pose=True,
            identity_hypotheses=sorted(hypotheses))
        return result

    def match(self,pixels):
        self.recognizer.floor_hint=self.floor_hint
        if hasattr(self.recognizer,"primary"):self.recognizer.primary.floor_hint=self.floor_hint
        identity=self.recognizer.match(pixels)
        known,message=presentation_candidate(identity)
        if known is None:
            if identity.reason in ('conflicting_reference_drawings','ambiguous_reference_drawings'):
                recovered=self.resolve_conflict(pixels,identity)
                if recovered is not None:return recovered
            # Do not let a route stroke break an unresolved identity tie.
            return self.standalone(pixels) or MatchResult(reason=identity.reason,diagnostics={'terrain_search':identity.to_dict()})
        support=next((r for r in self.recognizer.references if r.map_id==known.map_id),None)
        paired=[r for r in self.primary.references if r.recognition_map_id==known.map_id
                or (support is not None and support.terrain_id and r.terrain_id==support.terrain_id)]
        if not paired:
            return self.standalone(pixels) or MatchResult(reason='author_terrain_not_registered')
        self.primary.floor_hint=known.floor
        aligned=[]
        for ref in paired:
            result=self.primary.register_known(pixels,ref.map_id)
            candidate=cached_alignment_candidate(result)[0]
            if (candidate is not None and candidate.floor==known.floor
                    and candidate.explained>=.55 and candidate.contradiction<=.40
                    and candidate.retrieval_score>=4):aligned.append((candidate,result))
        if not aligned:
            return MatchResult(reason='author_route_alignment_failed',diagnostics={'terrain_search':identity.to_dict()})
        # Multiple drawings of the same full-coffin route are alternatives,
        # not different terrain identities. Their own alignment decides.
        candidate,result=max(aligned,key=lambda x:x[0].explained)
        if hasattr(self.primary,'ensure'):self.primary.ensure(candidate.map_id)
        result.candidates=[candidate]
        result.diagnostics['author_route']=dict(recognition_map_id=known.map_id,selected_map_id=candidate.map_id,independent_pose=True)
        return result


class LazyAuthorAtlas:
    """Keep metadata for the catalog, and evidence for at most one route atlas."""
    def __init__(self,index,matcher_type,*,difficulty,mode,provider):
        from .mapstore import read_manifest
        from .reference import Reference
        from .context import SessionContext
        SessionContext(difficulty,mode,provider)
        self.index=index;self.matcher_type=matcher_type
        self.difficulty=difficulty;self.mode=mode;self.provider=provider
        self.floor_hint=None;self.manual_scale_bounds=None
        self.loaded=None;self.loaded_id=None
        self.catalog=[Reference(e['map_id'],e['difficulty'],e['mode'],e['source'],None,None,
            e.get('regions',[]),e.get('exclude_regions',[]),e.get('terrain_id'),e.get('recognition_map_id'))
            for e in read_manifest(index) if e.get('provider','lianghapi')==provider
            and e['difficulty']==difficulty and e['mode']==mode]
        if not self.catalog:raise ValueError('当前地图库没有展十地图，请更新地图识别模块')
    @property
    def references(self):
        loaded={r.map_id:r for r in self.loaded.references} if self.loaded else {}
        return [loaded.get(r.map_id,r) for r in self.catalog]
    def ensure(self,map_id):
        if self.loaded is None or self.loaded_id!=map_id:
            self.loaded=None
            self.loaded=self.matcher_type(self.index,difficulty=self.difficulty,mode=self.mode,
                provider=self.provider,map_ids=[map_id] if map_id is not None else None)
            self.loaded_id=map_id
        self.loaded.floor_hint=self.floor_hint
        self.loaded.manual_scale_bounds=self.manual_scale_bounds
        return self.loaded
    def register_known(self,pixels,map_id):return self.ensure(map_id).register_known(pixels,map_id)
    def register_manual_floor(self,pixels,map_id,floor):return self.ensure(map_id).register_manual_floor(pixels,map_id,floor)
    def match(self,pixels):
        # Only used for locally enrolled, unpaired maps.
        return self.ensure(None).match(pixels)
