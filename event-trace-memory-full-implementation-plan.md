# Event Trace Memory for OmegaClaw / ASI Chain

**Implementation design for episodic event traces, content-addressed provenance, claim/feature extraction, pattern mining, and NAL/PLR ingestion**

**Version:** 0.1  
**Date:** 2026-06-27  
**Primary implementation target:** Rholang/F1R3FLY-style execution + external data availability layer  
**Design stance:** on-chain/index-contract as canonical pointer and trie-index anchor; DA layer as immutable payload store; miners/reasoners as explicit workers.

---

## 0. Executive summary

This implementation stores **event traces** as normalized, content-addressed records and exposes them through several independent indexes:

```text
time index       -> event ids
actor index      -> event ids
channel index    -> event ids
parent/causal    -> event ids
claim/feature    -> event ids / occurrence ids
pattern indexes  -> event ids / claim ids / occurrence ids
```

The system follows a strict split:

```text
Raw payload bytes / large artifacts     -> DA layer
Canonical event envelopes               -> DA layer
Contract state                           -> event ids, CIDs, path indexes, provenance anchors
Snapshot/materialized mining views       -> DA layer
Pattern mining                           -> explicit worker action
NAL/PLR updates                          -> explicit worker action
```

The central invariant is:

```text
Deduplication lives at canonical node identity.
Provenance lives at occurrence/run/event edges.
```

For example, if the same claim is extracted from 100 messages:

```text
1 ClaimNode
100 ClaimOccurrences
100 source-event links
1..n extraction-run links
```

This gives you dedup without losing auditability.

### 0.1 Executable implementation track

This repository should contain a **local reference implementation** before attempting a
networked Rholang/F1R3FLY deployment. The reference implementation is not a shortcut
around the architecture; it is the executable specification for the contracts,
workers, schemas, and acceptance criteria.

The reference implementation uses:

```text
Python package               -> event_trace_memory/
Filesystem DA store          -> content-addressed bytes under a configurable root
In-process contract indexes  -> deterministic stand-in for EventTraceIndex and DerivedArtifactIndex
JSON schemas                 -> schemas/
Worker APIs                  -> event ingestion, extraction, snapshotting, mining, reasoning
Acceptance tests             -> tests/
```

The implementation order is:

```text
1. canonical JSON, digests, CIDs, path prefixes
2. filesystem DA put/get
3. EventTraceIndex reference contract
4. ingestion worker and causal trace logging
5. DerivedArtifactIndex reference contract
6. claim/feature extraction artifacts with exact dedup and occurrence provenance
7. shard snapshot builder with local dictionaries and postings
8. itemset/sequence/motif pattern miners with support vectors
9. NAL/PLR adapter inputs and reasoning run logging
10. Rholang contract sketches kept aligned with the tested reference behavior
```

Every acceptance checkbox in section 20 should have a corresponding automated test.
The tests are the gate for commits. A deployment-specific Rholang implementation can
then be validated against the same fixtures and expected index behavior.

### 0.2 Concrete MVP decisions

These decisions remove ambiguity for the first implementation:

```text
CID format:
  cidv0-local-sha256:<hex-sha256>

Canonical JSON:
  UTF-8, sorted keys, compact separators, no NaN/Infinity

DA codec metadata:
  Stored alongside bytes in a manifest; CID identity is over bytes only

Prefix expansion:
  computed off-chain by worker/library and accepted by the reference contract

Contract sharding:
  single in-process index objects for MVP, with shard paths represented in snapshots

Privacy:
  public/plain path segments for MVP; hashed/encrypted paths remain a later extension

Semantic dedup:
  exact claim/feature/pattern identity first; reversible semantic clusters later

Vector search:
  vectors are DA artifacts only; no ANN implementation in the first acceptance pass
```

### 0.3 Acceptance test matrix

The first complete pass is accepted when the following tests pass:

```text
test_event_memory_acceptance
  duplicate event insertion rejection
  raw payload in DA
  canonical envelope in DA
  pointer-only contract storage
  time/actor/channel prefix queries
  parent/root trace queries

test_provenance_acceptance
  derived artifacts point to source events
  occurrences point to extraction runs
  extraction runs record code/prompt/model/config identity
  patterns point to mining runs and input snapshots
  reasoning outputs point to reasoning input and evidence

test_dedup_acceptance
  same payload CID recognized
  duplicate event id rejected
  same claim core creates one ClaimNode
  multiple evidence occurrences retained
  semantic near-duplicates represented by cluster nodes, not destructive merges

test_mining_acceptance
  mining consumes snapshots/postings
  support is counted with set intersections
  new events affect only their shard snapshot
  pattern results include support vectors

test_reasoning_acceptance
  NAL/PLR input contains claim plus evidence
  support vectors are available
  reasoning runs are logged as event traces
  belief/truth state is separate from ClaimNode identity
```

### 0.4 Commit discipline

Implementation should be committed and pushed in small slices:

```text
plan refinement
core package scaffolding
event memory acceptance
derived artifact/provenance acceptance
snapshot and mining acceptance
reasoning acceptance
documentation alignment
```

---

## 1. Conceptual basis from the papers

The papers do not dictate a software implementation, but they give several useful implementation disciplines.

### 1.1 Paths are subspaces

The path-keyed RSpace paper suggests representing channels as structured paths:

```text
["irc", "libera", "channel", "#chat"]
["agent", "omega-claw", "claim-extractor", "v0.1"]
["system", "memory", "long-term", "query"]
```

A prefix names a subspace:

```text
["irc"]                                      -> all IRC space
["irc", "libera"]                            -> all Libera IRC space
["irc", "libera", "channel"]                 -> all Libera channel space
["irc", "libera", "channel", "#chat"]        -> one channel
```

Implementation translation:

```text
Path prefix = queryable trie/index prefix
```

### 1.2 RSpace store versus explicit cuts

The RSpace papers distinguish inert store from explicit reaction. For this implementation:

```text
Event insertion is inert.
Claim extraction is an explicit action.
Feature extraction is an explicit action.
Pattern mining is an explicit action.
Reasoning/NAL/PLR update is an explicit action.
```

The system should **not** run every possible downstream computation automatically because a new event was inserted. Any triggering policy should be modeled as an explicit scheduler/worker and logged as an event trace.

### 1.3 Agency/apertures as logged choices

The nondeterminism/agency paper is useful for provenance: whenever the pipeline makes a meaningful choice, log it.

Examples:

```text
which extractor was used
which model/prompt/code version was used
which candidate claims were accepted
which semantic dedup cluster was chosen
which memory query result was selected
which pattern threshold was used
which PLR/NAL update policy was used
```

These are "apertures" in the pipeline: places where different admissible choices could have produced different downstream state.

### 1.4 Knotted names / nominalization

The knotted/rho papers motivate a uniform way to nominalize processes, events, and artifacts. In implementation terms:

```text
name(object) = content address of canonical representation
```

So:

```text
eventId      = hash(canonical event envelope)
claimId      = hash(canonical claim core)
featureId    = hash(canonical feature core)
patternId    = hash(canonical pattern core)
runId         = hash(canonical run envelope)
occurrenceId = hash(canonical occurrence envelope)
```

This gives a practical name system without primitive names.

---

## 2. System goals and non-goals

### 2.1 Goals

The implementation must support:

1. **Event trace ingestion**
   - user messages
   - agent actions
   - shell actions
   - memory queries
   - file reads
   - extraction runs
   - pattern mining runs
   - reasoning runs
   - outputs/responses

2. **Canonical content addressing**
   - raw payload CID
   - normalized event CID
   - event id from canonical envelope

3. **Multiple query axes**
   - by time
   - by actor
   - by channel
   - by parent/root trace
   - by event kind
   - by claim
   - by feature
   - by extractor
   - by pattern

4. **Deduplicated derived memory**
   - one canonical claim node for exact claim identity
   - many claim occurrences as evidence
   - one feature node for exact feature identity
   - many feature occurrences
   - reversible semantic clustering

5. **Efficient pattern mining**
   - no full raw-payload scans
   - prefix path filtering
   - compressed posting lists
   - shard snapshots
   - incremental updates

6. **NAL/PLR compatibility**
   - reason over claims plus evidence/support
   - keep raw provenance separate from current belief/truth state

### 2.2 Non-goals for the first implementation

The first implementation should not attempt:

```text
full semantic graph reasoning on-chain
large vector storage on-chain
on-chain ANN/vector search
automatic global reaction over the event store
destructive semantic deduplication
```

---

## 3. High-level architecture

```text
┌────────────────────┐
│ External Sources   │
│ IRC, shell, FS,    │
│ APIs, agents       │
└─────────┬──────────┘
          │
          v
┌────────────────────┐
│ Ingestion Worker   │
│ canonicalizes,     │
│ hashes, writes DA  │
└─────────┬──────────┘
          │ event pointer
          v
┌────────────────────┐
│ Rholang Index      │
│ Contract           │
│ events + indexes   │
└─────────┬──────────┘
          │ deltas / queries
          v
┌────────────────────┐
│ Snapshot Builder   │
│ shard materializer │
│ postings/columns   │
└─────────┬──────────┘
          │ snapshot CIDs
          v
┌────────────────────┐
│ Extractors         │
│ claims/features/   │
│ embeddings/entities│
└─────────┬──────────┘
          │ derived pointers
          v
┌────────────────────┐
│ Derived Artifact   │
│ Contract/Index     │
│ claims/features/   │
│ occurrences/runs   │
└─────────┬──────────┘
          │ snapshots
          v
┌────────────────────┐
│ Pattern Miners     │
│ itemsets/sequences │
│ motifs             │
└─────────┬──────────┘
          │ pattern nodes
          v
┌────────────────────┐
│ NAL/PLR Adapter    │
│ evidence vectors   │
│ truth updates      │
└────────────────────┘
```

---

## 4. Core design principles

### 4.1 Store large data in DA, not in the contract

The contract should not store raw message bodies, shell outputs, embeddings, or extraction logs. It should store compact pointers and indexes.

```text
DA stores:
  raw payloads
  canonical envelopes
  extraction outputs
  vectors
  shard snapshots
  posting lists
  pattern outputs

Contract stores:
  eventId
  eventCid
  payloadCid
  path keys
  index maps
  provenance anchors
```

### 4.2 Normalize once, index many times

An event node is stored once:

```text
events[eventId] -> EventPointer
```

Indexes store only IDs:

```text
timeIndex[prefixKey]    -> [eventId, ...]
actorIndex[prefixKey]   -> [eventId, ...]
channelIndex[prefixKey] -> [eventId, ...]
```

### 4.3 Use prefix keys instead of recursive trie objects on-chain

A full nested trie is conceptually clean, but a contract can be much simpler if it stores all prefixes as flat keys.

Path:

```json
["irc", "libera", "channel", "#chat"]
```

Canonical prefix keys:

```text
/irc
/irc/libera
/irc/libera/channel
/irc/libera/channel/%23chat
```

Then:

```text
channelIndex["/irc"]                         -> all IRC events
channelIndex["/irc/libera"]                  -> all Libera IRC events
channelIndex["/irc/libera/channel"]          -> all Libera channel events
channelIndex["/irc/libera/channel/%23chat"]  -> all #chat events
```

This is a trie map encoded as prefix postings. It preserves prefix query semantics while keeping contract logic small.

### 4.4 All derived computation is logged as event traces

Claim extraction is not merely an off-chain action. It becomes an event trace:

```text
actorPath:
  ["agent", "omega-claw", "extractor", "claim-extractor-v0.1"]

channelPath:
  ["system", "extraction", "claims"]

value:
  {
    "inputEventIds": [...],
    "outputClaimOccurrenceIds": [...],
    "runCid": "...",
    "status": "success"
  }
```

### 4.5 Dedup is exact first, semantic later

Exact dedup:

```text
claimId = hash(canonical claim core)
```

Semantic dedup:

```text
claimClusterId = hash(canonical cluster core)
```

Do not collapse semantic near-duplicates destructively. Use cluster nodes with reversible membership edges.

---

## 5. Canonicalization and identity

### 5.1 Canonical JSON

Use deterministic canonical JSON for every object that will be hashed.

Rules:

```text
UTF-8 encoding
sorted object keys
no insignificant whitespace
stable number representation
explicit schema version
explicit kind field
no unserialized runtime-only values
```

Recommended JSON canonicalization profile:

```text
JCS-style canonicalization or another formally specified canonical JSON profile
```

### 5.2 ID derivation

Recommended identities:

```text
payloadCid       = CID(raw observed payload)
eventCid         = CID(canonical event envelope)
eventId          = "event:" + digest(canonical event envelope)

runId            = "run:" + digest(canonical extraction/mining/reasoning run envelope)

claimCid         = CID(canonical claim core)
claimId          = "claim:" + digest(canonical claim core)

claimOccurrenceCid = CID(canonical claim occurrence)
claimOccurrenceId  = "claim-occ:" + digest(canonical claim occurrence)

featureCid       = CID(canonical feature core)
featureId        = "feature:" + digest(canonical feature core)

featureOccurrenceId = "feature-occ:" + digest(canonical feature occurrence)

patternCid       = CID(canonical pattern core)
patternId        = "pattern:" + digest(canonical pattern core)

patternOccurrenceId = "pattern-occ:" + digest(canonical pattern occurrence)
```

### 5.3 Event identity is not payload identity

Same raw payload may be interpreted under different schemas:

```text
payloadCid = CID(raw IRC line)
eventCid   = CID(normalized event envelope v0.1)
```

If the parser improves later:

```text
same payloadCid
new eventCid
new eventId
schema = event-trace-v0.2
```

This is a feature, not a bug. Raw observation and normalized interpretation are different artifacts.

---

## 6. Data model

### 6.1 Raw payload object

For an IRC message:

```json
{
  "kind": "raw-payload",
  "schema": "raw-irc-v0.1",
  "transport": "irc",
  "server": "libera",
  "room": "#chat",
  "nick": "alice",
  "message": "hello world",
  "raw": ":alice!user@host PRIVMSG #chat :hello world",
  "observedAt": "2026-06-27T14:35:00Z"
}
```

Stored in DA:

```text
payloadCid = CID(raw payload object)
```

### 6.2 Canonical event envelope

```json
{
  "kind": "event-trace",
  "schema": "event-trace-v0.1",

  "idPolicy": "eventId = digest(canonical envelope without id)",

  "time": {
    "iso": "2026-06-27T14:35:00Z",
    "year": 2026,
    "month": 6,
    "day": 27,
    "hour": 14,
    "minute": 35,
    "second": 0
  },

  "actorPath": ["irc", "libera", "user", "alice"],

  "channelPath": ["irc", "libera", "channel", "#chat"],

  "value": {
    "kind": "message",
    "contentType": "application/json",
    "payloadCid": "bafyPayload...",
    "preview": "hello world"
  },

  "provenance": {
    "source": "irc",
    "observedBy": "omega-claw",
    "ingestionPipeline": "event-trace-v0",
    "parser": {
      "name": "irc-event-parser",
      "version": "0.1.0",
      "codeCid": "bafyParserCode..."
    }
  },

  "causal": {
    "parentEventIds": [],
    "rootEventId": null,
    "inputEventIds": [],
    "outputArtifactIds": []
  }
}
```

Stored in DA:

```text
eventCid = CID(canonical event envelope)
eventId  = "event:" + digest(canonical event envelope)
```

### 6.3 Event pointer stored by contract

The contract stores:

```json
{
  "kind": "event-pointer",
  "schema": "event-pointer-v0.1",

  "eventId": "event:abc...",
  "eventCid": "bafyEvent...",
  "payloadCid": "bafyPayload...",

  "timePath": [2026, 6, 27, 14],
  "timePrefixKeys": [
    "/2026",
    "/2026/06",
    "/2026/06/27",
    "/2026/06/27/14"
  ],

  "actorPath": ["irc", "libera", "user", "alice"],
  "actorPrefixKeys": [
    "/irc",
    "/irc/libera",
    "/irc/libera/user",
    "/irc/libera/user/alice"
  ],

  "channelPath": ["irc", "libera", "channel", "#chat"],
  "channelPrefixKeys": [
    "/irc",
    "/irc/libera",
    "/irc/libera/channel",
    "/irc/libera/channel/%23chat"
  ],

  "valueKind": "message",
  "parentEventIds": [],
  "rootEventId": "event:abc..."
}
```

### 6.4 Extraction run

```json
{
  "kind": "extraction-run",
  "schema": "extraction-run-v0.1",

  "runType": "claim-extraction",

  "inputEventIds": ["event:abc..."],
  "inputArtifactCids": ["bafyEvent..."],

  "extractor": {
    "name": "omega-claw-claim-extractor",
    "version": "0.1.0",
    "codeCid": "bafyExtractorCode...",
    "promptCid": "bafyPrompt...",
    "model": {
      "name": "local-llm-x",
      "version": "2026-06-01",
      "weightsCid": "bafyWeights..."
    }
  },

  "config": {
    "claimSchema": "claim-core-v0.1",
    "includeEvidenceSpans": true,
    "minConfidence": 0.3
  },

  "startedAt": "2026-06-27T14:35:02Z",
  "completedAt": "2026-06-27T14:35:05Z",
  "status": "success",

  "outputCid": "bafyExtractionOutput..."
}
```

Identity:

```text
runId = "run:" + digest(canonical extraction-run envelope)
```

### 6.5 Claim core

The claim core is the normalized semantic proposition. It is not an occurrence and does not carry all evidence.

```json
{
  "kind": "claim",
  "schema": "claim-core-v0.1",

  "subject": {
    "type": "system-component",
    "id": "event-trace-store"
  },

  "predicate": {
    "id": "should-index-by"
  },

  "object": {
    "type": "index-set",
    "items": ["time", "actor", "channel"]
  },

  "modality": "normative",

  "context": {
    "domain": "episodic-memory-architecture"
  }
}
```

Identity:

```text
claimId = "claim:" + digest(canonical claim core)
```

### 6.6 Claim occurrence / attestation

```json
{
  "kind": "claim-occurrence",
  "schema": "claim-occurrence-v0.1",

  "claimId": "claim:abc...",
  "claimCid": "bafyClaim...",

  "sourceEventId": "event:source...",
  "sourceEventCid": "bafySourceEvent...",
  "sourcePayloadCid": "bafyRawPayload...",

  "extractionRunId": "run:extractor...",

  "evidence": {
    "kind": "text-span",
    "span": {
      "start": 0,
      "end": 64
    },
    "quote": "We should index event traces by time, actor, and channel."
  },

  "polarity": "asserted",
  "confidence": 0.82,

  "provenance": {
    "extractor": "omega-claw-claim-extractor",
    "extractorVersion": "0.1.0",
    "observedBy": "omega-claw"
  }
}
```

Identity:

```text
claimOccurrenceId =
  "claim-occ:" + digest(claimId + sourceEventId + evidence span + extractionRunId)
```

### 6.7 Feature core

Examples of features:

```text
topic
entity
embedding
sentiment
intent
relation candidate
source reliability feature
conversation state feature
```

Feature core example:

```json
{
  "kind": "feature",
  "schema": "feature-core-v0.1",
  "featureType": "topic",
  "value": {
    "id": "event-trace-indexing",
    "label": "event trace indexing"
  }
}
```

Embedding feature core:

```json
{
  "kind": "feature",
  "schema": "feature-core-v0.1",
  "featureType": "embedding",
  "model": {
    "name": "embedding-model-x",
    "version": "2026-06-01",
    "dimension": 768
  },
  "inputArtifactId": "event:abc...",
  "vectorDigest": "sha256:...",
  "vectorCid": "bafyVector..."
}
```

### 6.8 Feature occurrence

```json
{
  "kind": "feature-occurrence",
  "schema": "feature-occurrence-v0.1",

  "featureId": "feature:abc...",
  "sourceEventId": "event:source...",
  "extractionRunId": "run:feature-extraction...",

  "confidence": 0.91,

  "evidence": {
    "kind": "whole-event"
  }
}
```

### 6.9 Pattern core

A pattern is also a canonical node.

Sequence pattern example:

```json
{
  "kind": "pattern",
  "schema": "pattern-core-v0.1",

  "patternType": "sequence",

  "body": [
    {"eventKind": "user-message"},
    {"runKind": "memory-query"},
    {"runKind": "shell-action"},
    {"runKind": "claim-extraction"},
    {"artifactKind": "claim-occurrence"}
  ],

  "constraints": {
    "sameRootTrace": true,
    "maxWindowSeconds": 30
  }
}
```

### 6.10 Pattern occurrence

```json
{
  "kind": "pattern-occurrence",
  "schema": "pattern-occurrence-v0.1",

  "patternId": "pattern:abc...",
  "rootEventId": "event:root...",

  "participatingEventIds": [
    "event:e1",
    "event:e2",
    "event:e3",
    "event:e6"
  ],

  "participatingRunIds": ["run:r1"],
  "participatingClaimOccurrenceIds": ["claim-occ:o1"],

  "minedBy": "run:pattern-miner-..."
}
```

### 6.11 Pattern mining run

```json
{
  "kind": "pattern-mining-run",
  "schema": "pattern-mining-run-v0.1",

  "miningType": "sequence",

  "inputSnapshotCids": [
    "bafySnapshot2026062714..."
  ],

  "algorithm": {
    "name": "omega-sequence-miner",
    "version": "0.1.0",
    "codeCid": "bafyMinerCode..."
  },

  "config": {
    "minSupport": 5,
    "maxWindowSeconds": 30,
    "supportUnit": "root-trace"
  },

  "outputCid": "bafyPatternMiningOutput...",
  "startedAt": "2026-06-27T15:00:00Z",
  "completedAt": "2026-06-27T15:00:07Z",
  "status": "success"
}
```

---

## 7. Index design

### 7.1 Event indexes

Core event indexes:

```text
events[eventId] -> EventPointer

timeIndex[prefixKey] -> [eventId, ...]
actorIndex[prefixKey] -> [eventId, ...]
channelIndex[prefixKey] -> [eventId, ...]

eventKindIndex[valueKind] -> [eventId, ...]

parentIndex[parentEventId] -> [childEventId, ...]
rootTraceIndex[rootEventId] -> [eventId, ...]

payloadIndex[payloadCid] -> [eventId, ...]
eventCidIndex[eventCid] -> eventId
```

### 7.2 Derived artifact indexes

Claim/feature indexes:

```text
claims[claimId] -> ClaimPointer
claimOccurrences[occurrenceId] -> ClaimOccurrencePointer

occurrencesByClaim[claimId] -> [occurrenceId, ...]
occurrencesBySourceEvent[eventId] -> [occurrenceId, ...]
claimsBySubject[subjectKey] -> [claimId, ...]
claimsByPredicate[predicateKey] -> [claimId, ...]
claimsByObject[objectKey] -> [claimId, ...]

features[featureId] -> FeaturePointer
featureOccurrences[featureOccurrenceId] -> FeatureOccurrencePointer

featureOccurrencesByFeature[featureId] -> [featureOccurrenceId, ...]
featureOccurrencesBySourceEvent[eventId] -> [featureOccurrenceId, ...]
featuresByType[featureType] -> [featureId, ...]
```

Extraction/run indexes:

```text
runs[runId] -> RunPointer
runsByInputEvent[eventId] -> [runId, ...]
runsByOutputArtifact[artifactId] -> [runId, ...]
runsByExtractor[extractorKey] -> [runId, ...]
outputsByRun[runId] -> [artifactId, ...]
```

Pattern indexes:

```text
patterns[patternId] -> PatternPointer
patternOccurrences[patternOccurrenceId] -> PatternOccurrencePointer

occurrencesByPattern[patternId] -> [patternOccurrenceId, ...]
patternsByType[patternType] -> [patternId, ...]
patternsByInputSnapshot[snapshotCid] -> [patternId, ...]
patternsByMiner[minerKey] -> [patternId, ...]
```

### 7.3 Prefix key format

Use a stable path encoding.

Example actor path:

```json
["irc", "libera", "user", "alice"]
```

Encoded full key:

```text
/irc/libera/user/alice
```

Prefix keys:

```text
/irc
/irc/libera
/irc/libera/user
/irc/libera/user/alice
```

Rules:

```text
separator = "/"
escape "/" inside segment
percent-encode reserved characters
zero-pad numeric time segments
always include leading slash
no trailing slash except root
```

Time:

```text
[2026, 6, 27, 14]
```

Encoded:

```text
/2026
/2026/06
/2026/06/27
/2026/06/27/14
```

### 7.4 Sharding

Shard naturally by time:

```text
year shard:
  /2026

month shard:
  /2026/06

day shard:
  /2026/06/27

hour shard:
  /2026/06/27/14
```

Recommended operational layout:

```text
cold archive:     year/month
common analytics: day
online mining:    hour or smaller
hot ingestion:    minute/current root trace
```

Actor/channel sharding is also possible:

```text
actor shard:
  /irc/libera/user/alice

channel shard:
  /irc/libera/channel/%23chat
```

But time-based sharding should be the first physical partition, because ingestion and compaction are naturally chronological.

---

## 8. Rholang contract design

### 8.1 Contract role

The contract is the canonical index anchor.

It should:

```text
accept compact event pointers
reject duplicate event ids
update time/actor/channel/payload/parent/root indexes
return acknowledgements
support prefix-key queries
support id lookup
```

It should not:

```text
store raw payloads
store large event bodies
perform pattern mining
run claim extraction
store vectors
perform ANN search
```

### 8.2 Public API

EventTraceIndex API:

```text
putEvent(eventPointer, return)

getEvent(eventId, return)

byTimePrefix(timePrefixKey, return)
byActorPrefix(actorPrefixKey, return)
byChannelPrefix(channelPrefixKey, return)

byKind(valueKind, return)
byParent(parentEventId, return)
byRoot(rootEventId, return)
byPayloadCid(payloadCid, return)

getStateStats(return)
```

DerivedArtifactIndex API:

```text
putRun(runPointer, return)

putClaim(claimPointer, return)
putClaimOccurrence(occurrencePointer, return)

putFeature(featurePointer, return)
putFeatureOccurrence(featureOccurrencePointer, return)

putPattern(patternPointer, return)
putPatternOccurrence(patternOccurrencePointer, return)

bySourceEvent(eventId, return)
byClaim(claimId, return)
byFeature(featureId, return)
byRun(runId, return)
byExtractor(extractorKey, return)
byPattern(patternId, return)
```

### 8.3 MVP EventTraceIndex contract sketch

This is an implementation sketch. Validate against the exact target Rholang runtime because available collection methods and cost accounting may differ between implementations.

```rholang
new eventTraceIndex,
    stateCh,
    uriCh,
    insertArbitrary(`rho:registry:insertArbitrary`),
    stdout(`rho:io:stdout`)
in {

  /*
    State shape:

    {
      "events":       { eventId: eventPointer },
      "timeIndex":    { prefixKey: [eventId, ...] },
      "actorIndex":   { prefixKey: [eventId, ...] },
      "channelIndex": { prefixKey: [eventId, ...] },
      "kindIndex":    { valueKind: [eventId, ...] },
      "parentIndex":  { parentEventId: [childEventId, ...] },
      "rootIndex":    { rootEventId: [eventId, ...] },
      "payloadIndex": { payloadCid: [eventId, ...] },
      "eventCidIndex":{ eventCid: eventId }
    }
  */

  stateCh!({
    "events": {},
    "timeIndex": {},
    "actorIndex": {},
    "channelIndex": {},
    "kindIndex": {},
    "parentIndex": {},
    "rootIndex": {},
    "payloadIndex": {},
    "eventCidIndex": {}
  })

  |

  /*
    putEvent(eventPointer, return)

    eventPointer must include:
      eventId
      eventCid
      payloadCid
      valueKind
      timePrefixKeys
      actorPrefixKeys
      channelPrefixKeys
      parentEventIds
      rootEventId

    The ingestion worker precomputes prefix keys.
    A hardened version can verify them on-chain or require a signed ingest authority.
  */
  contract eventTraceIndex(@"putEvent", @eventPointer, return) = {
    for (@state <- stateCh) {

      eventId    = eventPointer.get("eventId") |
      eventCid   = eventPointer.get("eventCid") |
      payloadCid = eventPointer.get("payloadCid") |
      valueKind  = eventPointer.get("valueKind") |
      rootEventId = eventPointer.getOrElse("rootEventId", eventId) |

      if (state.getOrElse("events", {}).contains(eventId)) {
        stateCh!(state)
        |
        return!({
          "ok": false,
          "error": "duplicate-event-id",
          "eventId": eventId
        })
      } else {
        /*
          NOTE:
          Rholang collection iteration syntax varies by runtime/library.
          The following expresses the intended state update.

          Production implementation options:
            1. Precompute updated index maps off-chain and submit with proof/signature.
            2. Use a Rholang list fold helper.
            3. Store each prefix update as its own message to an index sub-contract.
        */

        new updatedTimeIndex,
            updatedActorIndex,
            updatedChannelIndex,
            updatedParentIndex
        in {
          /*
            Pseudocode helpers:

            appendAll(indexMap, prefixKeys, eventId)
            appendAll(parentIndex, parentEventIds, eventId)
          */

          updatedTimeIndex!(
            appendAll(
              state.getOrElse("timeIndex", {}),
              eventPointer.getOrElse("timePrefixKeys", []),
              eventId
            )
          )
          |
          updatedActorIndex!(
            appendAll(
              state.getOrElse("actorIndex", {}),
              eventPointer.getOrElse("actorPrefixKeys", []),
              eventId
            )
          )
          |
          updatedChannelIndex!(
            appendAll(
              state.getOrElse("channelIndex", {}),
              eventPointer.getOrElse("channelPrefixKeys", []),
              eventId
            )
          )
          |
          updatedParentIndex!(
            appendAll(
              state.getOrElse("parentIndex", {}),
              eventPointer.getOrElse("parentEventIds", []),
              eventId
            )
          )
          |

          for (
            @ti <- updatedTimeIndex;
            @ai <- updatedActorIndex;
            @ci <- updatedChannelIndex;
            @pi <- updatedParentIndex
          ) {
            stateCh!({
              "events":
                state.getOrElse("events", {}).set(eventId, eventPointer),

              "timeIndex": ti,
              "actorIndex": ai,
              "channelIndex": ci,

              "kindIndex":
                state.getOrElse("kindIndex", {}).set(
                  valueKind,
                  state.getOrElse("kindIndex", {}).getOrElse(valueKind, []) ++ [eventId]
                ),

              "parentIndex": pi,

              "rootIndex":
                state.getOrElse("rootIndex", {}).set(
                  rootEventId,
                  state.getOrElse("rootIndex", {}).getOrElse(rootEventId, []) ++ [eventId]
                ),

              "payloadIndex":
                state.getOrElse("payloadIndex", {}).set(
                  payloadCid,
                  state.getOrElse("payloadIndex", {}).getOrElse(payloadCid, []) ++ [eventId]
                ),

              "eventCidIndex":
                state.getOrElse("eventCidIndex", {}).set(eventCid, eventId)
            })
            |
            return!({
              "ok": true,
              "eventId": eventId,
              "eventCid": eventCid,
              "payloadCid": payloadCid
            })
          }
        }
      }
    }
  }

  |

  contract eventTraceIndex(@"getEvent", @eventId, return) = {
    for (@state <- stateCh) {
      stateCh!(state)
      |
      if (state.getOrElse("events", {}).contains(eventId)) {
        return!({
          "ok": true,
          "event": state.getOrElse("events", {}).get(eventId)
        })
      } else {
        return!({
          "ok": false,
          "error": "not-found",
          "eventId": eventId
        })
      }
    }
  }

  |

  contract eventTraceIndex(@"byTimePrefix", @prefixKey, return) = {
    for (@state <- stateCh) {
      stateCh!(state)
      |
      return!({
        "ok": true,
        "prefixKey": prefixKey,
        "eventIds": state.getOrElse("timeIndex", {}).getOrElse(prefixKey, [])
      })
    }
  }

  |

  contract eventTraceIndex(@"byActorPrefix", @prefixKey, return) = {
    for (@state <- stateCh) {
      stateCh!(state)
      |
      return!({
        "ok": true,
        "prefixKey": prefixKey,
        "eventIds": state.getOrElse("actorIndex", {}).getOrElse(prefixKey, [])
      })
    }
  }

  |

  contract eventTraceIndex(@"byChannelPrefix", @prefixKey, return) = {
    for (@state <- stateCh) {
      stateCh!(state)
      |
      return!({
        "ok": true,
        "prefixKey": prefixKey,
        "eventIds": state.getOrElse("channelIndex", {}).getOrElse(prefixKey, [])
      })
    }
  }

  |

  contract eventTraceIndex(@"byKind", @valueKind, return) = {
    for (@state <- stateCh) {
      stateCh!(state)
      |
      return!({
        "ok": true,
        "valueKind": valueKind,
        "eventIds": state.getOrElse("kindIndex", {}).getOrElse(valueKind, [])
      })
    }
  }

  |

  contract eventTraceIndex(@"byParent", @parentEventId, return) = {
    for (@state <- stateCh) {
      stateCh!(state)
      |
      return!({
        "ok": true,
        "parentEventId": parentEventId,
        "eventIds": state.getOrElse("parentIndex", {}).getOrElse(parentEventId, [])
      })
    }
  }

  |

  contract eventTraceIndex(@"byRoot", @rootEventId, return) = {
    for (@state <- stateCh) {
      stateCh!(state)
      |
      return!({
        "ok": true,
        "rootEventId": rootEventId,
        "eventIds": state.getOrElse("rootIndex", {}).getOrElse(rootEventId, [])
      })
    }
  }

  |

  contract eventTraceIndex(@"byPayloadCid", @payloadCid, return) = {
    for (@state <- stateCh) {
      stateCh!(state)
      |
      return!({
        "ok": true,
        "payloadCid": payloadCid,
        "eventIds": state.getOrElse("payloadIndex", {}).getOrElse(payloadCid, [])
      })
    }
  }

  |

  insertArbitrary!(bundle+{*eventTraceIndex}, *uriCh)
  |
  for (@uri <- uriCh) {
    stdout!(["EventTraceIndex URI: ", uri])
  }
}
```

### 8.4 Practical note on `appendAll`

The sketch uses a pseudocode helper:

```text
appendAll(indexMap, prefixKeys, eventId)
```

For a production Rholang deployment, use one of these approaches:

#### Option A: one sub-contract per index key

Represent each index key as a channel/cell:

```text
indexCell(prefixKey) contains [eventId, ...]
```

Then `putEvent` sends append messages to all affected prefix cells. This is more RSpace-like and naturally concurrent.

#### Option B: off-chain prefix expansion + signed state transition

The ingestion worker computes the prefixes and submits them. The contract only applies updates if the submitter has authority. This is easiest for MVP.

#### Option C: use a Rholang collection library

Use a runtime-supported list fold/map helper to update maps in-contract.

#### Option D: store only full keys on-chain, materialize prefix tries off-chain

This is cheapest but sacrifices direct on-chain prefix query. Acceptable if on-chain prefix queries are not required.

Recommended MVP:

```text
Option B + prefix keys stored on-chain
```

Recommended later version:

```text
Option A for high-concurrency index shards
```

---

## 9. Ingestion flow

### 9.1 Example: IRC message

Input:

```text
IRC server: libera
IRC channel: #chat
User: alice
Message: hello world
Timestamp: 2026-06-27T14:35:00Z
```

Step 1: raw payload object:

```json
{
  "kind": "raw-payload",
  "schema": "raw-irc-v0.1",
  "transport": "irc",
  "server": "libera",
  "room": "#chat",
  "nick": "alice",
  "message": "hello world",
  "raw": ":alice!user@host PRIVMSG #chat :hello world",
  "observedAt": "2026-06-27T14:35:00Z"
}
```

Step 2: write raw payload to DA:

```text
payloadCid = DA.put(canonicalRawPayload)
```

Step 3: canonical event envelope:

```json
{
  "kind": "event-trace",
  "schema": "event-trace-v0.1",
  "time": {
    "iso": "2026-06-27T14:35:00Z",
    "year": 2026,
    "month": 6,
    "day": 27,
    "hour": 14,
    "minute": 35,
    "second": 0
  },
  "actorPath": ["irc", "libera", "user", "alice"],
  "channelPath": ["irc", "libera", "channel", "#chat"],
  "value": {
    "kind": "message",
    "contentType": "application/json",
    "payloadCid": "bafyPayload...",
    "preview": "hello world"
  },
  "provenance": {
    "source": "irc",
    "observedBy": "omega-claw",
    "ingestionPipeline": "event-trace-v0"
  },
  "causal": {
    "parentEventIds": [],
    "rootEventId": null,
    "inputEventIds": [],
    "outputArtifactIds": []
  }
}
```

Step 4: write event envelope to DA:

```text
eventCid = DA.put(canonicalEventEnvelope)
eventId  = "event:" + digest(canonicalEventEnvelope)
```

Step 5: create contract event pointer:

```json
{
  "kind": "event-pointer",
  "schema": "event-pointer-v0.1",

  "eventId": "event:abc...",
  "eventCid": "bafyEvent...",
  "payloadCid": "bafyPayload...",

  "timePrefixKeys": [
    "/2026",
    "/2026/06",
    "/2026/06/27",
    "/2026/06/27/14"
  ],

  "actorPrefixKeys": [
    "/irc",
    "/irc/libera",
    "/irc/libera/user",
    "/irc/libera/user/alice"
  ],

  "channelPrefixKeys": [
    "/irc",
    "/irc/libera",
    "/irc/libera/channel",
    "/irc/libera/channel/%23chat"
  ],

  "valueKind": "message",
  "parentEventIds": [],
  "rootEventId": "event:abc..."
}
```

Step 6: call contract:

```rholang
eventTraceIndex!("putEvent", eventPointer, *ack)
```

### 9.2 Triggered actions as child event traces

Suppose the user message triggers:

```text
long-term memory query
shell action: read local file system
```

These become child events:

```text
e1 = user message

e2 = memory query started
  parentEventIds = [e1]
  actorPath = ["agent", "omega-claw", "memory-query-worker"]
  channelPath = ["system", "memory", "long-term", "query"]

e3 = shell action started
  parentEventIds = [e1]
  actorPath = ["agent", "omega-claw", "shell-worker"]
  channelPath = ["system", "shell", "filesystem", "read"]

e4 = memory query result
  parentEventIds = [e2]

e5 = shell action result
  parentEventIds = [e3]
```

This gives a trace graph:

```text
e1 user message
├── e2 memory query started
│   └── e4 memory result
└── e3 shell read started
    └── e5 shell output
```

If claim extraction then uses `e1`, `e4`, and `e5`:

```text
e6 extraction run event
  inputEventIds = [e1, e4, e5]
```

---

## 10. Derived artifact flow

### 10.1 Claim extraction

Input events:

```text
[e1, e4, e5]
```

Extraction run:

```text
run:r1
```

Claims emitted:

```text
claim:c1
claim:c2
```

Occurrences:

```text
claim-occ:o1 -> claim:c1 from source event e1 under run r1
claim-occ:o2 -> claim:c2 from source event e5 under run r1
```

Indexes updated:

```text
runs[run:r1] = RunPointer

claims[claim:c1] = ClaimPointer
claims[claim:c2] = ClaimPointer

claimOccurrences[o1] = OccurrencePointer
claimOccurrences[o2] = OccurrencePointer

occurrencesByClaim[claim:c1] += o1
occurrencesByClaim[claim:c2] += o2

occurrencesBySourceEvent[e1] += o1
occurrencesBySourceEvent[e5] += o2

runsByInputEvent[e1] += run:r1
runsByInputEvent[e4] += run:r1
runsByInputEvent[e5] += run:r1

outputsByRun[run:r1] += [o1, o2]
```

### 10.2 Feature extraction

Feature run:

```text
run:f1
```

Feature examples:

```text
feature:topic:event-traces
feature:entity:EventTraceStore
feature:embedding:e1-model-x
```

Occurrences:

```text
feature-occ:fo1 -> topic feature from e1
feature-occ:fo2 -> entity feature from e1
feature-occ:fo3 -> embedding feature from e1
```

Vectors live in DA/vector store:

```text
vectorCid = CID(vector bytes)
```

Contract stores:

```text
featureId
featureCid
vectorCid pointer
sourceEventId
runId
model identity
```

---

## 11. Snapshot builder

Pattern mining should not run directly over raw contract maps. Use snapshot materialization.

### 11.1 Snapshot unit

Recommended first unit:

```text
hour shard
```

Example:

```text
snapshot path = /2026/06/27/14
```

### 11.2 Snapshot contents

```json
{
  "kind": "mining-snapshot",
  "schema": "mining-snapshot-v0.1",

  "shardPath": "/2026/06/27/14",

  "eventDictionaryCid": "bafyEventDict...",
  "eventColumnsCid": "bafyEventColumns...",
  "postingsCid": "bafyPostings...",
  "provenanceEdgesCid": "bafyEdges...",
  "claimOccurrencesCid": "bafyClaimOccs...",
  "featureOccurrencesCid": "bafyFeatureOccs...",

  "sourceContract": "rho:id:...",
  "sourceIndexRoot": "optional-state-root-or-block-id",

  "createdAt": "2026-06-27T15:00:00Z"
}
```

### 11.3 Local integer dictionary

Inside a shard, map long IDs to integers:

```text
event:e1 -> 1
event:e2 -> 2
event:e3 -> 3
```

This makes postings compact:

```text
actor=/irc/libera/user/alice -> [1, 9, 15]
channel=/irc/libera/channel/%23chat -> [1, 2, 8, 9]
event.kind=message -> [1, 5, 9, 20]
claim=claim:abc -> [7, 11, 18]
```

### 11.4 Posting representation

Use one of:

```text
sorted integer lists
Roaring bitmaps
EWAH compressed bitmaps
run-length encoded bitsets
compressed sparse bitsets
```

The exact structure is DA-side and miner-side, not contract-side.

---

## 12. Pattern mining

### 12.1 Mining inputs

Pattern miners read:

```text
snapshot CIDs
contract query results
posting lists
local dictionaries
provenance edges
claim/feature occurrence tables
```

They do not scan all raw payloads.

### 12.2 Co-occurrence / itemset mining

Each event/root/session becomes a transaction of tokens:

```text
T_e1 = {
  "event.kind:message",
  "transport:irc",
  "actor:/irc/libera/user/alice",
  "channel:/irc/libera/channel/%23chat",
  "feature:topic:event-traces",
  "claim-predicate:should-index-by"
}
```

Support:

```text
support(A ∧ B ∧ C) = |postings(A) ∩ postings(B) ∩ postings(C)|
```

Example:

```text
S1 = postings("channel:/irc/libera/channel/%23chat")
S2 = postings("feature:topic:event-traces")
S3 = postings("claim-predicate:should-index-by")

support = |S1 ∩ S2 ∩ S3|
```

Efficient implementation:

```text
sort candidates by ascending posting length
intersect smallest first
prune if support < minSupport
```

### 12.3 Sequential / episode mining

Mine sequences over root traces:

```text
trace:e1 = [
  "event.kind:user-message",
  "run.kind:memory-query",
  "run.kind:shell-action",
  "run.kind:claim-extraction",
  "artifact.kind:claim-occurrence"
]
```

Pattern:

```text
user-message -> memory-query -> shell-action -> claim-extraction -> claim-occurrence
```

Support unit options:

```text
root trace
conversation
actor
channel
time bucket
event
```

Recommended first support unit:

```text
root trace
```

### 12.4 Graph motif mining

Use small provenance neighborhoods.

Example motif:

```text
UserMessage
  -> MemoryQuery
  -> ShellAction
  -> ClaimExtractionRun
      -> ClaimOccurrence
          -> ClaimNode
```

Implementation:

1. For each root event, extract depth-limited neighborhood.
2. Canonicalize labels and edge types.
3. Hash canonical motif.
4. Count motif occurrences.

```text
motifId = hash(canonical motif core)
motifIndex[motifId] -> [rootEventId, ...]
```

### 12.5 Support vectors

Do not store only one support number.

Use support vectors:

```json
{
  "occurrenceSupport": 10000,
  "eventSupport": 4000,
  "rootTraceSupport": 500,
  "actorSupport": 12,
  "channelSupport": 3,
  "daySupport": 7,
  "sourceSupport": 2,
  "extractorRunSupport": 4
}
```

This prevents evidence inflation from repeated messages by one bot or one extraction run.

### 12.6 Pattern output

A pattern miner emits:

```text
PatternMiningRun
PatternNode
PatternOccurrences
PatternDiscoveryEvent
```

The discovery itself is logged as an event trace:

```json
{
  "kind": "event-trace",
  "schema": "event-trace-v0.1",
  "actorPath": ["agent", "omega-claw", "pattern-miner", "sequence-v0"],
  "channelPath": ["system", "pattern-mining", "sequence"],
  "value": {
    "kind": "pattern-discovery",
    "patternId": "pattern:abc...",
    "patternCid": "bafyPattern...",
    "occurrencesCid": "bafyPatternOccurrences...",
    "supportVector": {
      "rootTraceSupport": 53,
      "actorSupport": 8,
      "channelSupport": 2
    }
  }
}
```

---

## 13. NAL / PLR adapter

### 13.1 Do not feed raw claims as truth

A `ClaimNode` is a normalized proposition-like object. It is not itself a belief state.

Use:

```text
claim = proposition identity
occurrences = evidence
reasoner state = current truth/belief valuation
```

### 13.2 Reasoning input object

```json
{
  "kind": "reasoning-input",
  "schema": "nal-plr-input-v0.1",

  "claimId": "claim:c1",
  "claimCid": "bafyClaim...",

  "statement": {
    "format": "nal-like",
    "text": "<event-trace-store --> indexable-by-time-actor-channel>"
  },

  "evidence": {
    "positiveOccurrences": ["claim-occ:o1", "claim-occ:o9"],
    "negativeOccurrences": ["claim-occ:o14"],
    "supportVector": {
      "eventSupport": 14,
      "actorSupport": 5,
      "channelSupport": 3,
      "daySupport": 6
    }
  },

  "derivedFromPatterns": ["pattern:p7", "pattern:p9"]
}
```

### 13.3 Reasoning run

A reasoning update is also an event:

```json
{
  "kind": "reasoning-run",
  "schema": "reasoning-run-v0.1",

  "reasoner": {
    "name": "plr-adapter",
    "version": "0.1.0",
    "codeCid": "bafyReasonerCode..."
  },

  "inputCids": ["bafyReasoningInput..."],
  "outputCid": "bafyReasonerOutput...",

  "config": {
    "revisionPolicy": "evidence-weighted",
    "decayPolicy": "time-decay-v0",
    "sourceReliabilityPolicy": "support-vector-v0"
  }
}
```

Then log an event trace:

```text
actorPath   = ["agent", "omega-claw", "reasoner", "plr-adapter-v0.1"]
channelPath = ["system", "reasoning", "plr"]
value.kind  = "reasoning-run"
```

---

## 14. Query examples

### 14.1 Events in one hour

```text
contract.byTimePrefix("/2026/06/27/14")
```

Returns:

```json
{
  "ok": true,
  "prefixKey": "/2026/06/27/14",
  "eventIds": ["event:e1", "event:e2", "event:e3"]
}
```

### 14.2 All events by actor Alice

```text
contract.byActorPrefix("/irc/libera/user/alice")
```

### 14.3 All Libera IRC channel events

```text
contract.byChannelPrefix("/irc/libera/channel")
```

### 14.4 Events in #chat by Alice during one hour

```text
S_time    = byTimePrefix("/2026/06/27/14")
S_actor   = byActorPrefix("/irc/libera/user/alice")
S_channel = byChannelPrefix("/irc/libera/channel/%23chat")

result = S_time ∩ S_actor ∩ S_channel
```

Intersection should be done off-chain over ID sets, or over compressed postings in a snapshot.

### 14.5 Claims extracted from an event

```text
derivedIndex.bySourceEvent("event:e1")
```

### 14.6 Evidence for a claim

```text
derivedIndex.byClaim("claim:c1")
```

Returns occurrence IDs. Load occurrence pointers, then source events, then raw payload CIDs if needed.

### 14.7 Patterns involving an actor/channel

1. Query events by actor/channel prefix.
2. Map to root traces.
3. Query pattern occurrences by root trace or scan snapshot motif indexes.
4. Return pattern IDs and support vectors.

---

## 15. Worker implementation outline

### 15.1 Ingestion worker

Responsibilities:

```text
receive source event
build raw payload object
canonicalize raw payload
write raw payload to DA
build canonical event envelope
write event envelope to DA
derive eventId
derive prefix keys
submit event pointer to Rholang contract
log ack/failure
```

Pseudocode:

```python
def ingest_irc_message(server, room, nick, message, raw, observed_at):
    raw_payload = {
        "kind": "raw-payload",
        "schema": "raw-irc-v0.1",
        "transport": "irc",
        "server": server,
        "room": room,
        "nick": nick,
        "message": message,
        "raw": raw,
        "observedAt": observed_at,
    }

    payload_cid = da_put(canonical_json(raw_payload))

    time_parts = parse_time(observed_at)
    actor_path = ["irc", server, "user", nick]
    channel_path = ["irc", server, "channel", room]

    event_envelope = {
        "kind": "event-trace",
        "schema": "event-trace-v0.1",
        "time": time_parts.full_object(),
        "actorPath": actor_path,
        "channelPath": channel_path,
        "value": {
            "kind": "message",
            "contentType": "application/json",
            "payloadCid": payload_cid,
            "preview": message[:160],
        },
        "provenance": {
            "source": "irc",
            "observedBy": "omega-claw",
            "ingestionPipeline": "event-trace-v0",
        },
        "causal": {
            "parentEventIds": [],
            "rootEventId": None,
            "inputEventIds": [],
            "outputArtifactIds": [],
        },
    }

    event_bytes = canonical_json(event_envelope)
    event_cid = da_put(event_bytes)
    event_id = "event:" + digest(event_bytes)

    pointer = {
        "kind": "event-pointer",
        "schema": "event-pointer-v0.1",
        "eventId": event_id,
        "eventCid": event_cid,
        "payloadCid": payload_cid,
        "timePrefixKeys": time_prefix_keys(time_parts),
        "actorPrefixKeys": path_prefix_keys(actor_path),
        "channelPrefixKeys": path_prefix_keys(channel_path),
        "valueKind": "message",
        "parentEventIds": [],
        "rootEventId": event_id,
    }

    return rholang_call("putEvent", pointer)
```

### 15.2 Extraction worker

Responsibilities:

```text
load event pointers
load event envelopes/payloads from DA
run extractor
canonicalize claim/feature cores
dedup by ID
create occurrences
write artifacts to DA
update derived artifact index
log extraction run as event trace
```

### 15.3 Snapshot builder

Responsibilities:

```text
fetch events for shard prefix
fetch derived artifact pointers
assign local integer ids
build columns
build postings
build provenance edge table
write snapshot to DA
log snapshot event
```

### 15.4 Pattern miner

Responsibilities:

```text
read snapshot
mine itemsets/sequences/motifs
emit pattern nodes and occurrences
write outputs to DA
update derived artifact index
log pattern mining run event
```

### 15.5 Reasoning adapter

Responsibilities:

```text
select claim/pattern evidence
build NAL/PLR input
submit to reasoner
write reasoning outputs to DA
log reasoning run event
```

---

## 16. Storage and availability

### 16.1 DA requirements

The DA layer should provide:

```text
content addressing
read by CID
write by bytes/object
pinning/replication
availability proofs or replication metadata if available
codec metadata
size metadata
digest metadata
```

### 16.2 Pointer metadata

Event pointers should include:

```json
{
  "cid": "bafy...",
  "codec": "dag-json",
  "size": 1234,
  "digest": "sha256:...",
  "availability": {
    "layer": "asi-da",
    "replication": "policy-id",
    "storageProof": "optional"
  }
}
```

### 16.3 CID is not availability

A CID proves content identity, not that someone still stores the bytes. Production requires pinning/replication policy.

---

## 17. Dedup strategy

### 17.1 Exact payload dedup

```text
payloadCid exists -> raw payload already known
```

### 17.2 Exact event dedup

```text
eventId exists -> same canonical event envelope already indexed
```

### 17.3 Exact claim dedup

```text
claimId exists -> do not create a second ClaimNode
```

Always create a new occurrence if a new extraction/evidence span supports the claim:

```text
claimId exists
occurrenceId does not exist
=> insert occurrence
```

### 17.4 Semantic dedup

Do not merge claim nodes destructively. Use cluster nodes:

```json
{
  "kind": "claim-cluster",
  "schema": "claim-cluster-v0.1",
  "relation": "semantic-near-duplicate",
  "members": ["claim:c1", "claim:c2", "claim:c3"],
  "method": {
    "name": "embedding-llm-human-review",
    "version": "0.1.0"
  },
  "confidence": 0.88
}
```

---

## 18. Security and trust model

### 18.1 Ingest authority

For MVP, assume trusted ingestion workers.

Production options:

```text
signed event pointers
registered ingest authorities
contract checks signatures
source-specific authentication
rate limits
stake/deposit for spam resistance
```

### 18.2 Event authenticity

Store:

```text
source signature if available
transport metadata
observer identity
ingestion code CID
timestamp source
```

### 18.3 Shell action safety

Shell actions must be explicitly permissioned and logged.

Shell action event should record:

```text
command or normalized action
working directory
allowlist policy
sandbox identity
start/end time
exit code
stdout CID
stderr CID
file read CIDs/digests
```

Do not store secrets in raw payloads or previews.

### 18.4 Privacy

Paths may leak information:

```text
actor path
channel path
payload preview
source metadata
```

Mitigation options:

```text
hash path segments
encrypt payloads
store private DA CIDs
use capability-gated lookup
store public indexes only for non-sensitive dimensions
separate confidential and public event stores
```

---

## 19. Operational deployment plan

### Phase 1: EventTraceIndex MVP

Deliver:

```text
DA put/get
canonical JSON
eventId derivation
prefix key derivation
Rholang EventTraceIndex contract
IRC ingestion worker
queries by time/actor/channel/event id
```

Acceptance:

```text
can ingest IRC "hello world"
can retrieve by event id
can retrieve by hour
can retrieve by actor prefix
can retrieve by channel prefix
event stored once
indexes store event ids only
raw payload retrievable from DA by CID
```

### Phase 2: Causal trace logging

Deliver:

```text
parent/root event support
memory query event traces
shell action event traces
result event traces
root trace query
```

Acceptance:

```text
given root event, retrieve full trace DAG
given child event, retrieve parent/root
shell output stored in DA, not contract
```

### Phase 3: Claim/feature extraction

Deliver:

```text
ExtractionRun schema
ClaimNode schema
ClaimOccurrence schema
FeatureNode schema
FeatureOccurrence schema
DerivedArtifactIndex
OmegaClaw claim extractor integration
```

Acceptance:

```text
same claim extracted twice -> one ClaimNode, two occurrences
given claim -> retrieve all occurrences
given source event -> retrieve claims/features
given extraction run -> retrieve outputs
```

### Phase 4: Snapshot builder

Deliver:

```text
hour shard snapshots
local event dictionary
posting lists
provenance edges
snapshot CID anchoring
```

Acceptance:

```text
can build snapshot for /YYYY/MM/DD/HH
can answer support query using postings
can reproduce snapshot from contract state/shard query
```

### Phase 5: Pattern mining

Deliver:

```text
itemset miner
sequence miner
small graph motif miner
PatternNode/Occurrence schemas
PatternMiningRun schema
pattern discovery event traces
```

Acceptance:

```text
detect recurring workflow:
  user-message -> memory-query -> shell-action -> claim-extraction
produce support vectors
link pattern occurrence to supporting events/runs/claims
```

### Phase 6: NAL/PLR adapter

Deliver:

```text
claim-to-NAL/PLR mapping
support vector conversion
reasoning input objects
reasoning run logs
reasoner output storage
```

Acceptance:

```text
reasoner input contains claim plus occurrences/support
reasoner output is traceable to evidence
contradictory claims remain separate evidence-bearing nodes
```

---

## 20. Acceptance criteria for the full implementation

The local reference implementation satisfies the following criteria through the
`python3 -m unittest discover -s tests` acceptance suite. A later deployed
Rholang/F1R3FLY implementation should be checked against the same behaviors.

### 20.1 Event memory

```text
[x] Event insertion rejects duplicate event ids.
[x] Raw payload is in DA.
[x] Canonical envelope is in DA.
[x] Contract stores event pointer only.
[x] Time prefix query works.
[x] Actor prefix query works.
[x] Channel prefix query works.
[x] Parent/root trace query works.
```

### 20.2 Provenance

```text
[x] Every derived artifact points to source events.
[x] Every occurrence points to an extraction run.
[x] Every extraction run records code/prompt/model/config identity.
[x] Every pattern points to mining run and input snapshots.
[x] Every reasoning output points to reasoning input and evidence.
```

### 20.3 Dedup

```text
[x] Same payload CID recognized.
[x] Same event id rejected/deduplicated.
[x] Same claim core creates one ClaimNode.
[x] Multiple evidence occurrences are retained.
[x] Semantic near-duplicates are clustered, not destructively merged.
```

### 20.4 Mining efficiency

```text
[x] Mining uses snapshots/postings, not raw full scans.
[x] Candidate sets are generated from prefix indexes.
[x] Support counting uses set intersections.
[x] New events update only affected shards.
[x] Pattern results include support vectors.
```

### 20.5 Reasoning integration

```text
[x] NAL/PLR receives claims with evidence, not raw truth assertions.
[x] Evidence support vectors are available.
[x] Reasoning runs are logged as event traces.
[x] Belief/truth state is separate from ClaimNode identity.
```

---

## 21. Example end-to-end trace

### 21.1 User message

```text
e1:
  actorPath   = /irc/libera/user/alice
  channelPath = /irc/libera/channel/%23chat
  value.kind  = message
  payload     = "hello world"
```

### 21.2 Triggered memory query

```text
e2:
  parent = e1
  actorPath   = /agent/omega-claw/memory-worker
  channelPath = /system/memory/long-term/query
  value.kind  = memory-query-start
```

### 21.3 Triggered shell action

```text
e3:
  parent = e1
  actorPath   = /agent/omega-claw/shell-worker
  channelPath = /system/shell/filesystem/read
  value.kind  = shell-action-start
```

### 21.4 Results

```text
e4:
  parent = e2
  value.kind = memory-query-result

e5:
  parent = e3
  value.kind = shell-action-result
```

### 21.5 Claim extraction

```text
e6:
  inputs = [e1, e4, e5]
  actorPath = /agent/omega-claw/extractor/claim-extractor-v0.1
  channelPath = /system/extraction/claims
  value.kind = extraction-run
```

### 21.6 Claim occurrence

```text
claim:c1:
  normalized proposition

claim-occ:o1:
  claimId = claim:c1
  sourceEventId = e1
  extractionRunId = run:r1
  evidence span = "hello world" or extracted relevant span
```

### 21.7 Pattern discovered later

```text
pattern:p1:
  user-message -> memory-query -> shell-action -> claim-extraction

pattern-occ:po1:
  rootEventId = e1
  participatingEventIds = [e1, e2, e3, e6]
```

---

## 22. Engineering checklist

### 22.1 Libraries/services

```text
canonical JSON library
hash/CID library
DA client
Rholang deploy/call client
posting-list/bitmap library
snapshot builder
claim extractor
feature extractor
pattern miner
NAL/PLR adapter
```

### 22.2 Repositories

Suggested layout:

```text
omega-memory/
  contracts/
    EventTraceIndex.rho
    DerivedArtifactIndex.rho

  schemas/
    event-trace-v0.1.schema.json
    event-pointer-v0.1.schema.json
    extraction-run-v0.1.schema.json
    claim-core-v0.1.schema.json
    claim-occurrence-v0.1.schema.json
    feature-core-v0.1.schema.json
    pattern-core-v0.1.schema.json
    pattern-occurrence-v0.1.schema.json
    reasoning-run-v0.1.schema.json

  workers/
    ingestion/
    extraction/
    snapshot-builder/
    pattern-miner/
    reasoning-adapter/

  da/
    client/
    codecs/

  tests/
    fixtures/
    integration/
    contract/
    mining/
```

This repository now includes versioned schema artifacts under `schemas/` for the
reference DA bodies, snapshot component maps, and compact contract pointers.
`tests/test_schema_artifacts.py` loads every `*.schema.json` file and validates
it against objects emitted by the current ingestion, derived artifact, snapshot,
pattern mining, and reasoning flows.

### 22.3 Test fixtures

Minimum fixtures:

```text
single IRC message
duplicate IRC message
same payload under different schema version
two messages same claim
one event with memory query and shell action
one extraction run with two claims
one hour snapshot with postings
one sequence pattern discovery
one NAL/PLR input generation
```

This repository now includes that minimum corpus in
`tests/fixtures/minimum-corpus-v0.1.json`. `tests/test_fixture_corpus.py` loads
the fixture data and executes it through the reference ingestion, artifact,
snapshot, pattern mining, and reasoning APIs.

### 22.4 Operator quickstart

This repository now includes an operator-facing fixture runner:

```bash
python3 -m event_trace_memory.cli run-fixture \
  --fixture tests/fixtures/minimum-corpus-v0.1.json \
  --da-root /tmp/event-trace-memory-da \
  --pretty
```

The console script entry point is `event-trace-memory` after package
installation. The root `README.md` documents the unit-test, fixture-summary, and
end-to-end fixture-runner commands.

### 22.5 Worker adapters

This repository now includes `event_trace_memory.workers` adapters for source
ingestion, memory query trace logging, shell action result logging, and
claim/feature extraction run logging. The shell adapter records observed command
results only; it does not execute commands. stdout/stderr bytes are stored in DA
and event traces keep only CIDs and compact metadata.

### 22.6 DA backend hardening

This repository now exposes a `DAStore` protocol with `FileDA` and `MemoryDA`
implementations. Both backends produce the same local SHA-256 CID format,
manifests, `stat(cid)` metadata, and `verify(cid)` integrity checks. The
reference APIs accept the protocol rather than a filesystem-only implementation.

### 22.7 Rholang deployment configuration

This repository now includes `configs/rholang-local-docker.json` and
`event_trace_memory.rholang_deployment` helpers for config-driven contract
deployment. `python3 -m event_trace_memory.cli rholang-plan` prints a redacted
deploy/propose plan, while `rholang-deploy` executes the same config through the
`RholangCli` wrapper.

### 22.8 Privacy policy

This repository now includes `PrivacyAwareIngestor` and `PublicIndexPolicy`.
Public ingestion rejects payloads marked `private`, `confidential`, or `secret`
before DA writes or index updates. Hashed-path ingestion supports public indexes
that hide actor/channel path labels; payload encryption remains an upstream
responsibility before publishing public pointers.

### 22.9 Scaling and sharding readiness

This repository now includes `event_trace_memory.scaling` helpers for event index
metrics, snapshot metrics, threshold-based sharding recommendations, and
delta-compressed posting lists. Contract sharding remains deferred until these
measurements cross explicit thresholds.

### 22.10 Advanced mining and reasoning

This repository now implements the full MVP mining surface from Phase 5:
sequence mining, posting-token itemset mining, and parent-child graph motif
mining over materialized snapshots. Itemset support is computed from snapshot
postings, graph motifs are computed from snapshot provenance edges, and pattern
occurrences preserve supporting events and claim occurrences.

The reasoning adapter also now writes DA-backed belief revision history artifacts
with ordered reasoning output states for a claim. Versioned JSON schemas cover
both revision-history bodies and pointers.

### 22.11 Belief revision history contract indexing

This repository now keeps belief revision histories aligned with the pointer
contract model. `DerivedArtifactIndex` stores compact revision-history pointers,
indexes them by claim and reasoning output, and exposes matching query methods in
both the Python reference contract and `contracts/DerivedArtifactIndex.rho`.
Runtime Rholang smoke generation now exercises the revision-history put/query
paths and verifies the new state counter.

### 22.12 Advanced fixture coverage

The minimum fixture corpus now exercises the advanced implementation paths end to
end. The fixture runner mines sequence, itemset, and parent-child graph motif
patterns from the same materialized snapshot, records multiple reasoning outputs,
stores an indexed belief revision history, and exposes all IDs/support vectors in
the CLI summary checks.

### 22.13 Fixture summary inspection

The CLI now supports `run-fixture --section all|patterns|reasoning|checks`.
Operators can inspect pattern support vectors or belief revision history IDs
without manually filtering the full fixture summary JSON. The default remains the
complete summary for backwards-compatible automation.

### 22.14 Reference index contract parity

The Python `DerivedArtifactIndex` stand-in now mirrors the Rholang contract query
families for miner runs, reasoner runs, pattern occurrences by root, and reasoning
outputs by input. Acceptance tests assert these helper APIs alongside the
existing direct index maps.

---

## 23. Resolved MVP design decisions

### 23.1 On-chain prefix expansion

Decision:

```text
Prefix keys are computed off-chain by trusted ingestion/snapshot workers and
submitted as part of event pointers for the MVP.
```

Rationale:

```text
The reference implementation and Rholang contracts already treat prefix keys as
compact pointer fields. On-chain recomputation or signature verification can be
added later without changing the event identity model because the canonical event
envelope remains in DA.
```

Future hardening:

```text
signed prefix manifests
on-chain prefix verification for public ingest authorities
capability-gated workers for private indexes
```

### 23.2 Contract sharding

Decision:

```text
Use one EventTraceIndex contract and one DerivedArtifactIndex contract for the
MVP. Represent shard paths in snapshots and materialized views, not as separate
contracts yet.
```

Deferred contract-per-shard layout:

```text
EventTraceIndexRoot
  -> TimeShard /2026/06/27/14
  -> ActorShard /irc/libera/user/alice
  -> ChannelShard /irc/libera/channel/%23chat
```

MVP baseline:

```text
single contract until index sizes justify sharding
```

Sharding trigger:

```text
Introduce contract shards only after measured index size, deploy cost, or query
cost requires it.
```

### 23.3 Private events

Decision:

```text
The MVP public event store accepts only non-sensitive fixture/demo data. Private
events are excluded from the public contract indexes until a capability-gated
private store is implemented.
```

Allowed later options:

```text
encrypted DA payloads
hashed path segments
private capability-controlled indexes
public indexes only for approved non-sensitive dimensions
```

### 23.4 Semantic dedup policy

Decision:

```text
Exact content identity is canonical for claims, features, patterns, runs, and
occurrences. Semantic near-duplicates are represented with reversible cluster
nodes and never destructively merged.
```

Implementation status:

```text
ClaimCluster pointers and clustersForClaim queries are implemented and tested.
The same claim core creates one ClaimNode while multiple evidence occurrences are
retained.
```

These decisions are recorded as ADR `docs/decisions/0001-mvp-operational-policies.md`.

---

## 24. Relationship to Rholang/RSpace execution

Rholang is process-oriented and uses asynchronous message passing on channels. The public Rholang documentation describes channels as bag/multiset-like rather than ordered queues, and notes that sends are asynchronous unless acknowledgement is explicitly modeled. This matches the event-trace design: ingestion sends a message to a contract channel and waits on an explicit return/ack channel.

The Rholang name registry pattern uses `rho:registry:insertArbitrary` to register a contract channel and return a URI. The EventTraceIndex sketch follows that deployment pattern.

References:

- Rholang documentation: https://rholang.org/docs/rholang/
- Rholang off-chain/name registry tutorial: https://rholang.org/tutorials/off-chain/
- Rholang repository: https://github.com/rchain/Rholang

---

## 25. Minimal first deliverable

The smallest useful implementation is:

```text
1. DA put/get
2. canonical JSON + CID generation
3. EventTraceIndex contract
4. IRC ingestion worker
5. byTimePrefix / byActorPrefix / byChannelPrefix queries
6. root/parent trace links
7. one fixture:
   IRC #chat alice "hello world"
   -> memory query event
   -> shell action event
```

This gives you a real episodic memory substrate.

The second deliverable should be:

```text
claim extractor
ClaimNode / ClaimOccurrence dedup/provenance
```

The third should be:

```text
hour snapshot builder
posting lists
first sequence pattern miner
```

---

## 26. Final invariant summary

Keep these invariants intact:

```text
1. Event traces are immutable, content-addressed observations/actions.
2. Raw bytes live in DA.
3. Contract stores IDs, CIDs, and indexes.
4. Time, actor, and channel are path-indexed.
5. Prefix keys give trie semantics.
6. Claim/feature nodes deduplicate exact semantic identities.
7. Occurrences preserve provenance.
8. Extraction/mining/reasoning runs are themselves event traces.
9. Pattern mining uses snapshots and postings, not raw scans.
10. NAL/PLR receives evidence-backed claims, not blind assertions.
11. No implicit global reaction: every downstream computation is an explicit logged action.
```

That is the implementation-level translation of the papers into an ASI-chain memory architecture:

```text
paths as subspaces
+ RSpace-style inert store
+ explicit cuts/actions
+ content-addressed nominalization
+ provenance-rich occurrences
+ efficient pattern mining snapshots
+ evidence-aware reasoning input
```
