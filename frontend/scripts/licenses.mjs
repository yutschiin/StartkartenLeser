import { existsSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

export function collectLicenses(root) {
  const projectRoot = resolve(root);
  const manifest = JSON.parse(readFileSync(join(projectRoot, "package.json"), "utf8"));
  const lock = JSON.parse(readFileSync(join(projectRoot, "package-lock.json"), "utf8"));
  const packages = new Map();

  function locate(name, from) {
    let directory = from;
    while (directory.startsWith(projectRoot)) {
      const candidate = join(directory, "node_modules", name);
      if (existsSync(join(candidate, "package.json"))) return candidate;
      if (directory === projectRoot) break;
      directory = dirname(directory);
    }
    return null;
  }

  function visit(name, from, optional = false) {
    const directory = locate(name, from);
    if (!directory) {
      if (optional) return;
      throw new Error(`Missing production dependency: ${name}`);
    }
    if (packages.has(directory)) return;
    const entry = JSON.parse(readFileSync(join(directory, "package.json"), "utf8"));
    const lockPath = relative(projectRoot, directory).split("\\").join("/");
    if (lock.packages?.[lockPath]?.version !== entry.version) {
      throw new Error(`Installed dependency does not match lockfile: ${lockPath}`);
    }
    const license = entry.license;
    if (typeof license !== "string" || !license.trim() ||
        /unknown|unlicensed|undefined|^none$/i.test(license)) {
      throw new Error(`Missing or unknown declared license: ${entry.name}@${entry.version}`);
    }
    const files = readdirSync(directory, { withFileTypes: true })
      .filter((file) => file.isFile() && /^(licen[cs]e|copying|notice)([._-].*)?$/i.test(file.name))
      .map((file) => file.name)
      .sort();
    if (!files.some((file) => /^(licen[cs]e|copying)([._-].*)?$/i.test(file))) {
      throw new Error(`Missing full license text: ${entry.name}@${entry.version}`);
    }
    const texts = files.map((file) => {
      const text = readFileSync(join(directory, file), "utf8").replace(/\r\n/g, "\n").trimEnd();
      if (!text.trim()) throw new Error(`Empty license/notice: ${lockPath}/${file}`);
      return `--- ${file} ---\n${text}\n`;
    });
    packages.set(directory, {
      path: lockPath,
      text: `${entry.name}@${entry.version}\nLicense: ${license}\nPackage: ${lockPath}\n\n${texts.join("\n")}`,
    });
    const dependencies = {
      ...entry.dependencies,
      ...entry.optionalDependencies,
      ...entry.peerDependencies,
    };
    for (const dependency of Object.keys(dependencies).sort()) {
      visit(
        dependency,
        directory,
        Object.hasOwn(entry.optionalDependencies ?? {}, dependency) ||
          Boolean(entry.peerDependenciesMeta?.[dependency]?.optional),
      );
    }
  }

  for (const name of Object.keys(manifest.dependencies ?? {}).sort()) visit(name, projectRoot);
  return "StartkartenLeser frontend — third-party licenses and notices\n" +
    "Installed production dependency closure, including installed optional peers.\n\n" +
    [...packages.values()]
      .sort((a, b) => a.path < b.path ? -1 : a.path > b.path ? 1 : 0)
      .map(({ text }) => `${"=".repeat(78)}\n${text}`)
      .join("\n");
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
  const text = collectLicenses(root);
  const output = resolve(root, "../src/startkartenleser/web_static/THIRD_PARTY_LICENSES.txt");
  writeFileSync(output, text, "utf8");
  console.log(`Collected frontend production licenses: ${output}`);
}
