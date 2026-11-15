import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import { resolve, join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { collectLicenses } from "../scripts/licenses.mjs";

const fixture = resolve("tests/.license-fixture");

function packageFile(directory, content) {
  mkdirSync(directory, { recursive: true });
  writeFileSync(join(directory, "package.json"), JSON.stringify(content));
}

function createFixture() {
  packageFile(fixture, { dependencies: { runtime: "1.0.0" }, devDependencies: { tooling: "1.0.0" } });
  writeFileSync(join(fixture, "package-lock.json"), JSON.stringify({
    packages: {
      "node_modules/runtime": { version: "1.0.0" },
      "node_modules/peer": { version: "1.0.0" },
    },
  }));
  const runtime = join(fixture, "node_modules/runtime");
  packageFile(runtime, {
    name: "runtime", version: "1.0.0", license: "MIT",
    peerDependencies: { peer: "*", absent: "*" },
    peerDependenciesMeta: { peer: { optional: true }, absent: { optional: true } },
  });
  writeFileSync(join(runtime, "LICENSE"), "Complete runtime license\n");
  writeFileSync(join(runtime, "NOTICE.txt"), "Runtime attribution\n");
  const peer = join(fixture, "node_modules/peer");
  packageFile(peer, { name: "peer", version: "1.0.0", license: "MIT" });
  writeFileSync(join(peer, "LICENSE.md"), "Complete peer license\n");
  packageFile(join(fixture, "node_modules/tooling"), { name: "tooling", version: "1.0.0" });
  return runtime;
}

afterEach(() => rmSync(fixture, { recursive: true, force: true }));

describe("production license collection", () => {
  it("includes full licenses, notices and installed optional peers, excluding dev-only packages", () => {
    createFixture();
    const text = collectLicenses(fixture);
    expect(text).toContain("Complete runtime license");
    expect(text).toContain("Runtime attribution");
    expect(text).toContain("Complete peer license");
    expect(text).not.toContain("tooling");
    expect(collectLicenses(fixture)).toBe(text);
  });

  it("fails explicitly for missing full license text", () => {
    const runtime = createFixture();
    rmSync(join(runtime, "LICENSE"));
    expect(() => collectLicenses(fixture)).toThrow("Missing full license text: runtime@1.0.0");
  });

  it("fails explicitly for unknown declarations", () => {
    const runtime = createFixture();
    packageFile(runtime, { name: "runtime", version: "1.0.0", license: "UNKNOWN" });
    expect(() => collectLicenses(fixture)).toThrow("Missing or unknown declared license");
  });

  it("collects the real installed runtime tree deterministically", () => {
    const output = collectLicenses(resolve("."));
    expect(output).toContain("@mui/material@");
    expect(output).toContain("@emotion/react@");
    expect(output).toContain("react-dom@");
    expect(output).not.toContain("Package: node_modules/vitest\n");
    expect(output).not.toContain("Package: node_modules/vite\n");
    expect(output).not.toContain("Package: node_modules/jsdom\n");
    expect(collectLicenses(resolve("."))).toBe(output);
  });
});
