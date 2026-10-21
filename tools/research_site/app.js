"use strict";
const root = document.body.dataset.root || "";
const current = document.body.dataset.page;
const activeLink = document.querySelector(`[data-nav="${current}"]`);
if (activeLink) {
  activeLink.classList.add("active");
  activeLink.setAttribute("aria-current", "page");
}
const escapeHTML = (value) =>
  String(value).replace(
    /[&<>"']/g,
    (char) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        char
      ],
  );
async function readJSON(name) {
  const response = await fetch(root + name);
  if (!response.ok) throw new Error(`无法读取 ${name}`);
  return response.json();
}
function showError(error) {
  const element = document.querySelector(".load-error");
  if (element) {
    element.hidden = false;
    element.textContent =
      "数据加载失败，请刷新重试。详细记录仍可通过资料页查看。";
  }
  console.error(error);
}
const definitions = {
  cpu_capacity_percent: {
    unit: "%",
    decimals: 2,
    note: "进程树占整机CPU容量；不是所有后台进程合计的CPU利用率。",
  },
  peak_pss_mib: {
    unit: " MiB",
    decimals: 2,
    note: "推理窗口内采样峰值PSS；主机进程树内存，不是NPU独占内存。",
  },
  ram_percent: {
    unit: "%",
    decimals: 2,
    note: "推理进程树峰值PSS / 本机实际MemTotal。",
  },
  compute_rtf: {
    unit: "",
    decimals: 3,
    note: "计算时间 / 音频时长，越小越快；不等于交互等待，实时回放的主动等待不计入计算。",
  },
};
function bar(label, subtitle, value, max, suffix, extra, type = "") {
  return `<div class="bar-row"><strong>${escapeHTML(label)}<small>${escapeHTML(subtitle)}</small></strong><div class="bar-track"><div class="bar-fill ${type}" style="width:${Math.max(0, Math.min(100, (value / max) * 100))}%"></div></div><output>${escapeHTML(suffix)}<small>${escapeHTML(extra)}</small></output></div>`;
}
if (current === "index" || current === "models")
  readJSON("data.json")
    .then((data) => {
      if (current === "index") {
        const rows = ["cpu", "rknn"].map((backend) =>
          data.comparisons.find(
            (r) => r.scenario === "realtime" && r.backend === backend,
          ),
        );
        document.querySelector("#overview-cpu").textContent = rows
          .map((r) => r.values.cpu_capacity_percent.median.toFixed(1) + "%")
          .join(" / ");
        document.querySelector("#overview-quality").textContent = data.quality
          .map((r) => (r.quality.cer * 100).toFixed(2) + "%")
          .join(" → ");
        return;
      }
      let metric = "cpu_capacity_percent";
      const scenario = document.querySelector("#scenario");
      function render() {
        const rows = data.comparisons.filter(
          (r) => r.scenario === scenario.value,
        );
        if (rows.length !== 2) throw new Error("Unexpected comparison group");
        const definition = definitions[metric];
        const max = Math.max(...rows.map((r) => r.values[metric].max)) * 1.15;
        document.querySelector("#comparison-chart").innerHTML = rows
          .map((r) => {
            const values = r.values[metric];
            const format = (n) => n.toFixed(definition.decimals);
            return bar(
              r.backend === "cpu" ? "CPU方案" : "NPU方案",
              r.backend === "cpu" ? "混合INT8 · ONNX" : "FP16 · RKNN",
              values.median,
              max,
              format(values.median) + definition.unit,
              `${r.rounds}轮 · ${format(values.min)}–${format(values.max)}`,
              r.backend === "cpu" ? "" : "npu",
            );
          })
          .join("");
        document.querySelector("#metric-note").textContent = definition.note;
        const cpu = rows.find((r) => r.backend === "cpu").values[metric].median;
        const npu = rows.find((r) => r.backend === "rknn").values[metric]
          .median;
        const format = (value) =>
          value.toFixed(definition.decimals) + definition.unit;
        const scope = scenario.value === "realtime" ? "实时回放" : "非实时供音";
        const descriptions = {
          cpu_capacity_percent:
            "占用更少的CPU容量，可能为LLM、TTS留下余量；但实际共跑是否改善仍需匹配实验。",
          peak_pss_mib:
            "PSS更高的方案需要更多主机驻留内存。是否值得，要结合CPU余量、其他进程和质量判断，不能称为NPU独占内存。",
          ram_percent:
            "这表示相对于本机实际RAM的占比。剩余空间还需要容纳LLM、TTS、视觉和系统，不能把未占用比例全部当成可分配预算。",
          compute_rtf:
            "RTF小于1表示本测量范围内处理比音频时长短，但不代表说完即可得到最终文字；端点与排队也影响等待。",
        };
        document.querySelector("#metric-interpretation").textContent =
          `${scope}下，CPU方案为${format(cpu)}，NPU方案为${format(npu)}。${descriptions[metric]} 两者精度不同，这里不归因纯后端收益。`;
      }
      scenario.addEventListener("change", render);
      document.querySelectorAll("[data-metric]").forEach((button) =>
        button.addEventListener("click", () => {
          metric = button.dataset.metric;
          document.querySelectorAll("[data-metric]").forEach((other) => {
            other.classList.toggle("active", other === button);
            other.setAttribute("aria-pressed", String(other === button));
          });
          render();
        }),
      );
      render();
      document.querySelector("#quality-chart").innerHTML = data.quality
        .map((r, i) =>
          bar(
            i ? "INT8 joiner" : "浮点joiner",
            "encoder/decoder FP16",
            r.quality.cer * 100,
            100,
            (r.quality.cer * 100).toFixed(2) + "%",
            `${r.quality.character_errors}/${r.quality.reference_characters} 字符错误`,
            i ? "" : "npu",
          ),
        )
        .join("");
      document.querySelector("#transcripts").innerHTML = data.quality
        .map(
          (r, i) =>
            `<div><strong>${i ? "INT8 joiner候选" : "浮点joiner控制"}</strong><p>${escapeHTML(r.samples.find((s) => s.case_id === "command").transcript)}</p></div>`,
        )
        .join("");
    })
    .catch(showError);
if (current === "evidence")
  readJSON("search.json")
    .then((entries) => {
      const input = document.querySelector("#search");
      const render = () => {
        const query = input.value.trim().toLocaleLowerCase();
        const results = entries.filter((entry) =>
          entry.title.toLocaleLowerCase().includes(query),
        );
        document.querySelector("#search-results").innerHTML = results.length
          ? results
              .map(
                (entry) =>
                  `<a href="${escapeHTML(root + entry.path)}">${escapeHTML(entry.title)} ↗</a>`,
              )
              .join("")
          : '<p class="muted">没有找到匹配标题，试试“部署”“ASR”或“量化”。</p>';
      };
      input.addEventListener("input", render);
      render();
    })
    .catch(showError);
