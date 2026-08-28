import assert from "node:assert/strict";
import test from "node:test";
import {
  citationChipLabel,
  parseCitationTag,
  resolveCitation,
  splitCitedParts,
  type CitationLike,
} from "./citations.ts";

const pageCitation: CitationLike = {
  tag: "source_1",
  filename: "paper.pdf",
  page_number: 4,
  content: "Indexed page excerpt.",
};

const stampCitation: CitationLike = {
  tag: "source_2",
  filename: "lecture.mp4",
  timestamp: 91,
  content: "Indexed transcript excerpt.",
};

test("backend citation tags are 1-indexed", () => {
  assert.deepEqual(parseCitationTag("[source_1]"), { key: "source_1", index: 1 });
  assert.equal(parseCitationTag("[source_0]"), null);
});

test("first citation [source_1] resolves the first retrieved chunk", () => {
  const citation = resolveCitation("[source_1]", [pageCitation, stampCitation]);
  assert.equal(citation?.filename, "paper.pdf");
  assert.equal(citation?.page_number, 4);
  assert.equal(citationChipLabel(citation, 1), "paper.pdf");
});

test("multiple citations resolve independently by tag, not by array offset of the tag number", () => {
  const usedOnlySecond = [stampCitation];
  assert.equal(resolveCitation("[source_2]", usedOnlySecond)?.filename, "lecture.mp4");
  assert.equal(resolveCitation("[source_1]", usedOnlySecond), undefined);
  assert.equal(
    resolveCitation("[source_2]", [pageCitation, stampCitation])?.timestamp,
    91,
  );
});

test("missing citations stay unresolved instead of shifting to a neighbor", () => {
  assert.equal(resolveCitation("[source_3]", [pageCitation, stampCitation]), undefined);
  assert.equal(resolveCitation("[source_1]", []), undefined);
  assert.equal(citationChipLabel(undefined, 3), "Source 3");
});

test("page citations keep page_number provenance", () => {
  const citation = resolveCitation("source_1", [pageCitation]);
  assert.equal(citation?.page_number, 4);
  const parts = splitCitedParts("See [source_1] for the table.");
  assert.equal(parts[1].type, "citation");
  if (parts[1].type === "citation") assert.equal(parts[1].index, 1);
});

test("timestamp citations keep timestamp provenance", () => {
  const citation = resolveCitation("[source_2]", {
    source_1: pageCitation,
    source_2: stampCitation,
  });
  assert.equal(citation?.timestamp, 91);
  assert.equal(citation?.filename, "lecture.mp4");
});

test("citation maps from streaming chat use source_N keys", () => {
  const citation = resolveCitation("[source_1]", undefined, { source_1: pageCitation });
  assert.equal(citation?.filename, "paper.pdf");
});
