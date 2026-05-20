/**
 * india-ethanol-mcp — HTTP MCP Server
 * Vercel API route: /api/mcp
 *
 * 7 tools. No Anthropic/OpenAI dependency.
 * The analyze tool calls your own LLM endpoint (configured via env var).
 *
 * Claude Desktop config:
 * {
 *   "mcpServers": {
 *     "india-ethanol": {
 *       "type": "http",
 *       "url": "https://YOUR_PROJECT.vercel.app/api/mcp",
 *       "headers": { "X-API-Key": "iem_YOUR_KEY" }
 *     }
 *   }
 * }
 */

const TOOLS = [
  {
    name: "get_ebp_prices",
    description:
      "Get current EBP (Ethanol Blending Programme) procurement prices " +
      "as notified by CCEA. Sources verified against PIB press releases. " +
      "Feedstocks: C_heavy_molasses, B_heavy_molasses, sugarcane_juice, " +
      "damaged_grains, maize, FCI_rice. Prices in ₹/litre.",
    inputSchema: {
      type: "object",
      properties: {
        season: {
          type: "string",
          description: "Sugar season e.g. 2024-25 (default: latest)",
        },
        feedstock: {
          type: "string",
          enum: ["C_heavy_molasses","B_heavy_molasses","sugarcane_juice",
                 "damaged_grains","maize","FCI_rice"],
          description: "Specific feedstock (optional — returns all if omitted)",
        },
        compare: {
          type: "boolean",
          description: "Include price delta vs previous season",
        },
      },
    },
  },
  {
    name: "get_blending_achievement",
    description:
      "Get monthly national ethanol blending achievement vs EBP target. " +
      "Data sourced from PPAC Monthly Oil & Gas Snapshots (6-8 week lag). " +
      "Shows whether India is on track for its 18-20% blending target. " +
      "ESY (Ethanol Supply Year) runs November to October.",
    inputSchema: {
      type: "object",
      properties: {
        esy: {
          type: "string",
          description: "Ethanol Supply Year e.g. 2024-25",
        },
        state: {
          type: "string",
          description: "Filter to specific state e.g. Uttar Pradesh",
        },
        months: {
          type: "number",
          description: "How many months of history to return (default 12)",
        },
      },
    },
  },
  {
    name: "get_omc_tenders",
    description:
      "Get OMC ethanol procurement tenders (IOCL, BPCL, HPCL). " +
      "Shows tender volumes, bid timelines, and current status. " +
      "OMCs float national tenders every ESY with depot-wise requirements. " +
      "Note: Depot-wise allocation quantities are OMC-confidential. " +
      "For actual bidding: portal.ethanolforindia.com",
    inputSchema: {
      type: "object",
      properties: {
        esy: { type: "string", description: "Ethanol Supply Year" },
        omc: {
          type: "string",
          enum: ["IOCL","BPCL","HPCL"],
          description: "Specific OMC",
        },
        status: {
          type: "string",
          enum: ["upcoming","active","awarded","closed"],
        },
      },
    },
  },
  {
    name: "get_omc_depots",
    description:
      "Get OMC depot locations for supply logistics planning. " +
      "Distilleries typically supply within 200-500km radius. " +
      "Use this to identify which depots you can competitively serve — " +
      "closer depot = lower freight = better margin.",
    inputSchema: {
      type: "object",
      properties: {
        omc: {
          type: "string",
          enum: ["IOCL","BPCL","HPCL"],
        },
        state: {
          type: "string",
          description: "Filter depots by state",
        },
      },
    },
  },
  {
    name: "get_ccea_notifications",
    description:
      "Get CCEA and MoPNG policy notifications for the ethanol sector. " +
      "Scraped from PIB press releases — updated within 24hrs of notification. " +
      "Covers: annual price revisions (October), policy changes, blending target updates. " +
      "Replaces manual monitoring of government sites.",
    inputSchema: {
      type: "object",
      properties: {
        category: {
          type: "string",
          enum: ["price_revision","policy","target_change"],
        },
        limit: {
          type: "number",
          description: "Number of notifications to return (default 10)",
        },
      },
    },
  },
  {
    name: "optimize_sugar_vs_ethanol",
    description:
      "Calculate optimal diversion for a sugar mill: produce sugar or divert to ethanol? " +
      "Uses live CCEA prices fetched from database — not hardcoded. " +
      "Returns revenue comparison for both scenarios, recommendation, and breakeven price.",
    inputSchema: {
      type: "object",
      properties: {
        cane_crushed_tonnes: {
          type: "number",
          description: "Total cane crushed in tonnes",
        },
        sugar_recovery_pct: {
          type: "number",
          description: "Sugar recovery percentage e.g. 10.5",
        },
        ethanol_yield_litre_per_tonne: {
          type: "number",
          description: "Ethanol yield in litres per tonne of cane e.g. 72",
        },
        feedstock: {
          type: "string",
          enum: ["C_heavy_molasses","B_heavy_molasses","sugarcane_juice"],
        },
        ex_mill_sugar_price_inr_quintal: {
          type: "number",
          description: "Current ex-mill sugar price in ₹/quintal",
        },
        season: {
          type: "string",
          description: "Sugar season e.g. 2024-25",
        },
      },
      required: [
        "cane_crushed_tonnes","sugar_recovery_pct",
        "ethanol_yield_litre_per_tonne","feedstock",
        "ex_mill_sugar_price_inr_quintal"
      ],
    },
  },
  {
    name: "analyze_ethanol_market",
    description:
      "AI-powered market analysis grounded on live EBP data. " +
      "Ask strategic questions such as: " +
      "'Should I bid on UP cluster tenders this ESY?', " +
      "'What is the revenue outlook for a 100 KLPD B-heavy plant in Maharashtra?', " +
      "'Which states are underperforming on blending targets?'. " +
      "Returns data-driven analytical narrative — not generic advice. " +
      "Requires Starter tier API key or above.",
    inputSchema: {
      type: "object",
      properties: {
        query: {
          type: "string",
          description: "Your strategic question about the ethanol market",
        },
        context: {
          type: "object",
          description: "Optional context about your operation",
          properties: {
            distillery_state: { type: "string" },
            feedstock: { type: "string" },
            capacity_klpd: { type: "number" },
            esy: { type: "string" },
          },
        },
      },
      required: ["query"],
    },
  },
];

// ── API helper ─────────────────────────────────────────────────────────────

async function callAPI(path, params = {}, method = "GET", body = null) {
  const apiKey = process.env.GRIDINTELIN_API_KEY;
  const baseUrl = process.env.GRIDINTELIN_API_URL || "https://ethanol.gridintelin.com";

  const url = new URL(`${baseUrl}${path}`);
  url.searchParams.set("api_key", apiKey);
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null) url.searchParams.set(k, String(v));
  }

  const opts = { method, headers: { "Content-Type": "application/json" } };
  if (body) opts.body = JSON.stringify(body);

  const res = await fetch(url.toString(), opts);
  const json = await res.json();
  if (!res.ok) throw new Error(json.error || `API error ${res.status}`);
  return json.data;
}

// ── Tool router ────────────────────────────────────────────────────────────

async function handleTool(name, args) {
  switch (name) {
    case "get_ebp_prices":
      return await callAPI("/api/v1/ethanol/prices", args);

    case "get_blending_achievement":
      return await callAPI("/api/v1/ethanol/blending", args);

    case "get_omc_tenders":
      return await callAPI("/api/v1/ethanol/tenders", args);

    case "get_omc_depots":
      return await callAPI("/api/v1/ethanol/depots", args);

    case "get_ccea_notifications":
      return await callAPI("/api/v1/ethanol/notifications", args);

    case "optimize_sugar_vs_ethanol":
      return await callAPI("/api/v1/ethanol/optimize", {}, "POST", args);

    case "analyze_ethanol_market":
      return await callAPI("/api/v1/ethanol/analyze", {}, "POST", args);

    default:
      throw new Error(`Unknown tool: ${name}`);
  }
}

// ── Vercel HTTP handler ────────────────────────────────────────────────────

export default async function handler(req, res) {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "POST, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type, X-API-Key, x-api-key");

  if (req.method === "OPTIONS") return res.status(200).end();
  if (req.method !== "POST") {
    return res.status(405).json({ error: "Method not allowed. MCP requires POST." });
  }

  let body;
  try {
    body = typeof req.body === "string" ? JSON.parse(req.body) : req.body;
  } catch {
    return res.status(400).json({ error: "Invalid JSON" });
  }

  const { method, params, id } = body || {};

  if (method === "initialize") {
    return res.status(200).json({
      jsonrpc: "2.0",
      id,
      result: {
        protocolVersion: "2024-11-05",
        capabilities: { tools: {} },
        serverInfo: { name: "india-ethanol-mcp", version: "0.1.0" },
      },
    });
  }

  if (method === "tools/list") {
    return res.status(200).json({
      jsonrpc: "2.0",
      id,
      result: { tools: TOOLS },
    });
  }

  if (method === "tools/call") {
    const { name, arguments: args } = params || {};
    if (!name) {
      return res.status(400).json({
        jsonrpc: "2.0", id,
        error: { code: -32602, message: "Tool name required" },
      });
    }
    try {
      const result = await handleTool(name, args || {});
      return res.status(200).json({
        jsonrpc: "2.0",
        id,
        result: {
          content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
        },
      });
    } catch (e) {
      return res.status(200).json({
        jsonrpc: "2.0",
        id,
        result: {
          content: [{ type: "text", text: `Error: ${e.message}` }],
          isError: true,
        },
      });
    }
  }

  return res.status(400).json({
    jsonrpc: "2.0",
    id,
    error: { code: -32601, message: `Unknown method: ${method}` },
  });
}
