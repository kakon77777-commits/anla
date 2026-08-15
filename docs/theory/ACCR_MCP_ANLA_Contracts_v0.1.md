# ACCR MCP / ANLA Contracts v0.1

## MCP rule

MCP is the transport bus.

ACCR runtime state is explicit.

Every state-dependent request includes the appropriate handle.

## Proposed ACCR tools

### accR.status

Input:

```json
{}
```

Output includes:

```text
runtime_version
database_health
archive_health
maintenance_backlog
governor_checkpoint
```

### accr.ingest

Input:

```json
{
  "context_run_id": "ctx_...",
  "branch_id": "branch_main",
  "object_type": "conversation_turn",
  "content_ref": "...",
  "source": {},
  "persistence_class": "active"
}
```

Output:

```text
canonical_id
digest
projection_job_id
archive_job_id
```

### accr.prepare_context

Input:

```json
{
  "context_run_id": "ctx_...",
  "query": "...",
  "budget": {
    "max_input_tokens": 64000
  }
}
```

Output:

```text
plan_id
items
omitted
metrics
```

### accr.expand

Input:

```json
{
  "canonical_ids": ["obj_..."],
  "verify": true
}
```

Output:

```text
canonical objects / bytes / verified digest
```

### accr.commit

Input:

```json
{
  "context_run_id": "ctx_...",
  "plan_id": "plan_...",
  "events": []
}
```

### accr.recheck

Input:

```json
{
  "canonical_ids": ["obj_..."],
  "reason": "upstream_superseded"
}
```

## ANLA read adapter

Current connected surface is sufficient for read-side MVP operations:

```text
context_status
context_project
context_find
context_address
context_expand
anla_verify
anla_snapshots
anla_diff
anla_manifest
```

## ANLA writer gap

Current connected surface does not expose a full pack/append writer lifecycle.

Define internal interface:

```text
ArchiveWriterAdapter.append(canonical_object)
ArchiveWriterAdapter.snapshot()
ArchiveWriterAdapter.verify()
```

Implementation may call:

```text
local ANLA CLI
local daemon
future MCP writer
```

The read contract remains unchanged.

## Candidate resolution

Preferred path:

```text
query
 -> context_find or semantic index
 -> context_address
 -> canonical_id resolver
 -> hard gate
 -> governor
 -> context_expand
```

## Exact expansion rule

ANLA expansion result is mapped back to canonical object.

Returned bytes are accepted as authoritative only after expected digest verification when a digest is available.

## Failure behavior

If ANLA search fails:

```text
fallback candidate backend
```

If ANLA expansion fails:

```text
alternate canonical replica
```

If no verified replica is available:

```text
do not silently regenerate authoritative source
return source_unavailable
```
