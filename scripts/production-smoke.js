#!/usr/bin/env node
/*
 * AtlasLM production readiness smoke test.
 *
 * Runs against the deployed web API by default:
 *   node scripts/production-smoke.js
 *
 * Optional env:
 *   ATLAS_SMOKE_BASE_URL=https://www.atlaslm.cloud
 *   ATLAS_SMOKE_SKIP_YOUTUBE=1
 *   ATLAS_SMOKE_IMAGE_PATH=C:\path\to\image.png
 *   ATLAS_SMOKE_YOUTUBE_1=https://youtu.be/...
 *   ATLAS_SMOKE_YOUTUBE_2=https://youtu.be/...
 */

const fs = require("fs");
const path = require("path");
const zlib = require("zlib");

const ROOT = path.resolve(__dirname, "..");
const BASE_URL = process.env.ATLAS_SMOKE_BASE_URL || "https://www.atlaslm.cloud";
const SKIP_YOUTUBE = process.env.ATLAS_SMOKE_SKIP_YOUTUBE === "1";
const DEFAULT_YOUTUBE_URLS = [
  "https://youtu.be/RL_PDX_BVxw?si=n677CYk09fqLTNie",
  "https://youtu.be/QQEgIo4Juxg?si=oZdiZYQisWzsd-Ht",
];

function loadEnvFile(filePath) {
  if (!fs.existsSync(filePath)) return {};
  const env = {};
  for (const raw of fs.readFileSync(filePath, "utf8").split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith("#") || !line.includes("=")) continue;
    const idx = line.indexOf("=");
    const key = line.slice(0, idx).trim();
    let value = line.slice(idx + 1).trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    env[key] = value;
  }
  return env;
}

function loadEnv() {
  return {
    ...loadEnvFile(path.join(ROOT, ".env.local")),
    ...loadEnvFile(path.join(ROOT, "frontend", ".env.local")),
    ...process.env,
  };
}

function tinyPngBuffer() {
  const width = 96;
  const height = 64;
  const rows = [];
  for (let y = 0; y < height; y += 1) {
    const row = Buffer.alloc(1 + width * 3);
    row[0] = 0;
    for (let x = 0; x < width; x += 1) {
      const offset = 1 + x * 3;
      const inBlock = x > 18 && x < 78 && y > 14 && y < 50;
      row[offset] = inBlock ? 20 : 245;
      row[offset + 1] = inBlock ? 132 : 245;
      row[offset + 2] = inBlock ? 88 : 245;
    }
    rows.push(row);
  }

  const signature = Buffer.from("89504e470d0a1a0a", "hex");
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr[8] = 8;
  ihdr[9] = 2;
  ihdr[10] = 0;
  ihdr[11] = 0;
  ihdr[12] = 0;

  return Buffer.concat([
    signature,
    pngChunk("IHDR", ihdr),
    pngChunk("IDAT", zlib.deflateSync(Buffer.concat(rows))),
    pngChunk("IEND", Buffer.alloc(0)),
  ]);
}

function pngChunk(type, data) {
  const typeBuffer = Buffer.from(type, "ascii");
  const length = Buffer.alloc(4);
  length.writeUInt32BE(data.length, 0);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(Buffer.concat([typeBuffer, data])), 0);
  return Buffer.concat([length, typeBuffer, data, crc]);
}

function crc32(buffer) {
  let crc = 0xffffffff;
  for (const byte of buffer) {
    crc ^= byte;
    for (let i = 0; i < 8; i += 1) {
      crc = (crc >>> 1) ^ (0xedb88320 & -(crc & 1));
    }
  }
  return (crc ^ 0xffffffff) >>> 0;
}

async function parseResponse(res) {
  const text = await res.text();
  try {
    return text ? JSON.parse(text) : null;
  } catch {
    return text;
  }
}

async function jsonFetch(url, options = {}) {
  const res = await fetch(url, options);
  const body = await parseResponse(res);
  if (!res.ok) {
    const preview = typeof body === "string" ? body.slice(0, 400) : JSON.stringify(body).slice(0, 400);
    throw new Error(`${options.method || "GET"} ${url} -> ${res.status}: ${preview}`);
  }
  return body;
}

function check(results, name, passed, detail = "") {
  results.checks.push({ name, passed: Boolean(passed), detail });
}

async function createTempUser(env) {
  const supabaseUrl = env.SUPABASE_URL || env.NEXT_PUBLIC_SUPABASE_URL;
  const anonKey = env.NEXT_PUBLIC_SUPABASE_ANON_KEY || env.SUPABASE_ANON_KEY;
  const serviceRoleKey = env.SUPABASE_SERVICE_ROLE_KEY;
  if (!supabaseUrl || !anonKey || !serviceRoleKey) {
    throw new Error("Missing Supabase smoke env. Need SUPABASE_URL, anon key, and service role key.");
  }

  const stamp = Date.now();
  const email = `atlas_smoke_${stamp}@example.com`;
  const password = `AtlasSmoke${stamp}!`;

  const created = await jsonFetch(`${supabaseUrl}/auth/v1/admin/users`, {
    method: "POST",
    headers: {
      apikey: serviceRoleKey,
      Authorization: `Bearer ${serviceRoleKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ email, password, email_confirm: true }),
  });

  const login = await jsonFetch(`${supabaseUrl}/auth/v1/token?grant_type=password`, {
    method: "POST",
    headers: { apikey: anonKey, "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });

  return {
    supabaseUrl,
    serviceRoleKey,
    userId: created.id,
    token: login.access_token,
  };
}

async function deleteTempUser(session) {
  if (!session?.userId) return;
  await fetch(`${session.supabaseUrl}/auth/v1/admin/users/${session.userId}`, {
    method: "DELETE",
    headers: {
      apikey: session.serviceRoleKey,
      Authorization: `Bearer ${session.serviceRoleKey}`,
    },
  }).catch(() => {});
}

async function pollDocument(headers, workspaceId, documentId, timeoutMs = 90000) {
  const started = Date.now();
  let latest = null;
  while (Date.now() - started < timeoutMs) {
    const docs = await jsonFetch(`${BASE_URL}/api/v1/workspaces/${workspaceId}/documents`, { headers });
    latest = docs.find((doc) => doc.id === documentId) || latest;
    if (latest && latest.status !== "processing") return latest;
    await new Promise((resolve) => setTimeout(resolve, 3000));
  }
  return latest;
}

async function pollStudio(headers, workspaceId, outputId, timeoutMs = 90000) {
  const started = Date.now();
  let latest = null;
  while (Date.now() - started < timeoutMs) {
    latest = await jsonFetch(`${BASE_URL}/api/v1/workspaces/${workspaceId}/studio/${outputId}`, { headers });
    if (latest.status !== "pending" && latest.status !== "processing") return latest;
    await new Promise((resolve) => setTimeout(resolve, 3000));
  }
  return latest;
}

function youtubeUrls() {
  const urls = [process.env.ATLAS_SMOKE_YOUTUBE_1, process.env.ATLAS_SMOKE_YOUTUBE_2]
    .filter(Boolean);
  return urls.length ? urls : DEFAULT_YOUTUBE_URLS;
}

async function main() {
  const env = loadEnv();
  const results = { baseUrl: BASE_URL, checks: [], artifacts: {} };
  let session = null;

  try {
    session = await createTempUser(env);
    const headers = {
      Authorization: `Bearer ${session.token}`,
      "Content-Type": "application/json",
    };

    const workspace = await jsonFetch(`${BASE_URL}/api/v1/workspaces`, {
      method: "POST",
      headers,
      body: JSON.stringify({ name: "Production Smoke Notebook" }),
    });
    results.artifacts.workspaceId = workspace.id;
    check(results, "workspace.create", Boolean(workspace.id));

    const textDoc = await jsonFetch(`${BASE_URL}/api/v1/workspaces/${workspace.id}/documents/text`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        title: "Atlas Orion facts",
        content: "Atlas Orion is the internal codename for this AtlasLM production readiness test. The launch owner is KLAW Labs.",
      }),
    });
    check(results, "source.text.ready", textDoc.status === "ready", textDoc.status);

    const websiteDoc = await jsonFetch(`${BASE_URL}/api/v1/workspaces/${workspace.id}/documents/url`, {
      method: "POST",
      headers,
      body: JSON.stringify({ url: "https://example.com" }),
    });
    check(results, "source.website.accepted", Boolean(websiteDoc.id), websiteDoc.status || "");
    const finalWebsite = websiteDoc.status === "processing"
      ? await pollDocument(headers, workspace.id, websiteDoc.id, 60000)
      : websiteDoc;
    check(results, "source.website.ready", finalWebsite?.status === "ready", finalWebsite?.error_message || finalWebsite?.status || "missing");

    const imagePath = process.env.ATLAS_SMOKE_IMAGE_PATH;
    const imageBuffer = imagePath && fs.existsSync(imagePath)
      ? fs.readFileSync(imagePath)
      : tinyPngBuffer();
    const imageForm = new FormData();
    imageForm.append("file", new Blob([imageBuffer], { type: "image/png" }), "atlas-smoke.png");
    const imageRes = await fetch(`${BASE_URL}/api/v1/workspaces/${workspace.id}/documents`, {
      method: "POST",
      headers: { Authorization: `Bearer ${session.token}` },
      body: imageForm,
    });
    const imageBody = await parseResponse(imageRes);
    check(results, "source.image.accepted", imageRes.ok && Boolean(imageBody?.id), imageBody?.detail || imageRes.status);
    const finalImage = imageRes.ok && imageBody?.status === "processing"
      ? await pollDocument(headers, workspace.id, imageBody.id, 90000)
      : imageBody;
    check(results, "source.image.ready", finalImage?.status === "ready", finalImage?.error_message || finalImage?.status || "missing");

    if (!SKIP_YOUTUBE) {
      let index = 1;
      for (const url of youtubeUrls()) {
        const res = await fetch(`${BASE_URL}/api/v1/workspaces/${workspace.id}/documents/youtube`, {
          method: "POST",
          headers,
          body: JSON.stringify({ url }),
        });
        const body = await parseResponse(res);
        check(results, `source.youtube.${index}.accepted`, res.ok && Boolean(body?.id), body?.detail || res.status);
        const finalDoc = res.ok && body?.status === "processing"
          ? await pollDocument(headers, workspace.id, body.id, 180000)
          : body;
        check(results, `source.youtube.${index}.ready`, finalDoc?.status === "ready", finalDoc?.error_message || finalDoc?.status || "missing");
        index += 1;
      }
    } else {
      check(results, "source.youtube.skipped", true, "ATLAS_SMOKE_SKIP_YOUTUBE=1");
    }

    const sessionRow = await jsonFetch(`${BASE_URL}/api/v1/workspaces/${workspace.id}/sessions`, {
      method: "POST",
      headers,
      body: JSON.stringify({ title: "Smoke Chat" }),
    });
    const chatRes = await fetch(`${BASE_URL}/api/v1/sessions/${sessionRow.id}/chat/stream`, {
      method: "POST",
      headers,
      body: JSON.stringify({ content: "What is the internal codename and who owns the launch?" }),
    });
    const chatText = await chatRes.text();
    check(results, "chat.grounded.no_error", chatRes.ok && !chatText.includes("event: error"), chatText.slice(0, 160).replace(/\s+/g, " "));
    check(results, "chat.grounded.answer", /Atlas Orion/i.test(chatText) && /KLAW Labs/i.test(chatText));

    const studio = await jsonFetch(`${BASE_URL}/api/v1/workspaces/${workspace.id}/studio`, {
      method: "POST",
      headers,
      body: JSON.stringify({ output_type: "study_guide" }),
    });
    const finalStudio = await pollStudio(headers, workspace.id, studio.id, 120000);
    check(results, "studio.study_guide.ready", finalStudio?.status === "ready" && Boolean(finalStudio?.content), finalStudio?.error || finalStudio?.status || "missing");

    const audioRes = await fetch(`${BASE_URL}/api/v1/workspaces/${workspace.id}/audio/generate`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        title: "Smoke Audio Overview",
        style: "brief",
        voice: "atlas-offline",
        doc_ids: [textDoc.id],
      }),
    });
    const audioBody = await parseResponse(audioRes);
    check(results, "audio.generate", audioRes.ok && Boolean(audioBody?.audio_url), audioBody?.detail || audioRes.status);
    if (audioRes.ok && audioBody?.audio_url) {
      const streamRes = await fetch(`${BASE_URL}${audioBody.audio_url}`, {
        headers: { Authorization: `Bearer ${session.token}` },
      });
      const bytes = (await streamRes.arrayBuffer()).byteLength;
      check(results, "audio.stream", streamRes.ok && bytes > 10000, `${streamRes.status}, ${bytes} bytes`);
    }
  } finally {
    await deleteTempUser(session);
  }

  const failed = results.checks.filter((item) => !item.passed);
  console.log(JSON.stringify(results, null, 2));
  if (failed.length) {
    console.error(`AtlasLM production smoke failed: ${failed.length} check(s).`);
    process.exit(1);
  }
}

main().catch((error) => {
  console.error(JSON.stringify({ ok: false, error: error.message }, null, 2));
  process.exit(1);
});
