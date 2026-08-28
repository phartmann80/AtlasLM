/**
 * AtlasLM citation tags are 1-indexed: [source_1] is the first retrieved
 * chunk. Chat and Studio reports must resolve with the same helper.
 */

export type CitationLike = {
  tag?: string;
  filename?: string;
  page_number?: number;
  timestamp?: number;
  content?: string;
  text?: string;
  quote?: string;
  source_url?: string | null;
  source_label?: string;
  [key: string]: unknown;
};

const TAG_RE = /^\[?(source_(\d+))\]?$/;

export function parseCitationTag(value: string): { key: string; index: number } | null {
  const match = value.trim().match(TAG_RE);
  if (!match) return null;
  const index = Number(match[2]);
  if (!Number.isInteger(index) || index < 1) return null;
  return { key: match[1], index };
}

export function splitCitedParts(content: string): Array<
  { type: "text"; value: string } | { type: "citation"; tag: string; index: number }
> {
  return content.split(/(\[source_\d+\])/g).map((part) => {
    const parsed = parseCitationTag(part);
    if (part.match(/^\[source_\d+\]$/) && parsed) {
      return { type: "citation", tag: parsed.key, index: parsed.index };
    }
    return { type: "text", value: part };
  });
}

function asCitation(value: unknown): CitationLike | undefined {
  if (!value || typeof value !== "object") return undefined;
  return value as CitationLike;
}

export function resolveCitation(
  tag: string,
  citations?: CitationLike[] | Record<string, CitationLike> | null,
  citationMap?: Record<string, CitationLike> | null,
): CitationLike | undefined {
  const parsed = parseCitationTag(tag);
  if (!parsed) return undefined;
  const { key, index } = parsed;

  const fromMap = citationMap?.[key] || citationMap?.[`[${key}]`];
  if (fromMap) return fromMap;

  if (citations && !Array.isArray(citations)) {
    return citations[key] || citations[`[${key}]`] || citations[String(index)];
  }

  const list = Array.isArray(citations) ? citations : [];
  const byTag = list.find((item) => {
    const itemTag = typeof item?.tag === "string" ? parseCitationTag(item.tag) : null;
    return itemTag?.key === key || itemTag?.index === index;
  });
  if (byTag) return byTag;

  if (list.some((item) => typeof item?.tag === "string")) {
    return undefined;
  }

  return asCitation(list[index - 1]);
}

export function citationChipLabel(citation: CitationLike | undefined, index: number): string {
  if (citation?.filename) return citation.filename;
  return `Source ${index}`;
}
