import { createTool } from "@mastra/core/tools";
import { z } from "zod";

export type AtlasHeaders = {
  context: string;
  signature: string;
};

const atlasApiUrl = () => (process.env.ATLAS_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

export async function atlasCall<T>(
  headers: AtlasHeaders,
  toolName: string,
  body: unknown,
): Promise<T> {
  const response = await fetch(`${atlasApiUrl()}/internal/atlas/tools/${toolName}`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "X-Atlas-Internal-Context": headers.context,
      "X-Atlas-Internal-Signature": headers.signature,
    },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(`Atlas tool ${toolName} failed with ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function createAtlasTools(headers: AtlasHeaders) {
  return {
    getNotebookContext: createTool({
      id: "getNotebookContext",
      description: "Load the current authorized notebook summary and source readiness counts.",
      inputSchema: z.object({}),
      execute: async () => atlasCall(headers, "getNotebookContext", {}),
    }),
    listAuthorizedSources: createTool({
      id: "listAuthorizedSources",
      description: "List only ready sources that the authenticated Atlas user may access.",
      inputSchema: z.object({}),
      execute: async () => atlasCall(headers, "listAuthorizedSources", {}),
    }),
    retrieveSourceExcerpts: createTool({
      id: "retrieveSourceExcerpts",
      description: "Retrieve relevant, authorized excerpts for the user's question.",
      inputSchema: z.object({
        query: z.string().min(1).max(4000),
        source_ids: z.array(z.string().uuid()).nullable().optional(),
        top_k: z.number().int().min(1).max(24).optional(),
      }),
      execute: async (context) => atlasCall(headers, "retrieveSourceExcerpts", context),
    }),
    getSourceMetadata: createTool({
      id: "getSourceMetadata",
      description: "Get metadata for a set of authorized source IDs.",
      inputSchema: z.object({ source_ids: z.array(z.string().uuid()) }),
      execute: async (context) => atlasCall(headers, "getSourceMetadata", context.source_ids),
    }),
    saveConversationTurn: createTool({
      id: "saveConversationTurn",
      description: "Persist an authorized notebook conversation turn and its citations.",
      inputSchema: z.object({
        session_id: z.string().uuid(),
        role: z.enum(["user", "assistant"]),
        content: z.string().min(1),
        citations: z.array(z.record(z.string(), z.unknown())).optional(),
        trace_id: z.string().optional(),
      }),
      execute: async (context) => atlasCall(headers, "saveConversationTurn", context),
    }),
    saveGeneratedOutput: createTool({
      id: "saveGeneratedOutput",
      description: "Persist a generated report and its verified citations in Atlas Studio.",
      inputSchema: z.object({
        output_id: z.string().uuid(),
        run_id: z.string().uuid(),
        output_type: z.string(),
        title: z.string(),
        content: z.unknown(),
        citations: z.array(z.record(z.string(), z.unknown())),
        source_scope: z.array(z.string().uuid()).nullable().optional(),
        status: z.enum(["ready", "failed"]),
        error: z.string().nullable().optional(),
        progress: z.number().int().min(0).max(100),
      }),
      execute: async (context) => atlasCall(headers, "saveGeneratedOutput", context),
    }),
    verifyCitationReferences: createTool({
      id: "verifyCitationReferences",
      description: "Verify that every citation points to an authorized indexed source chunk.",
      inputSchema: z.object({
        citations: z.array(z.record(z.string(), z.unknown())),
      }),
      execute: async (context) => atlasCall(headers, "verifyCitationReferences", context),
    }),
  };
}
