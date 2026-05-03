import { defineConfig } from "orval";

export default defineConfig({
  fastsaas: {
    input: "../backend/openapi.json",
    output: {
      mode: "tags-split",
      target: "src/api/generated/",
      client: "react-query",
      mock: { type: "msw" },
      override: {
        mutator: { path: "src/lib/api/client.ts", name: "apiClient" },
      },
    },
  },
});
