import type { Granularity } from "./types";

export const MODE_DESCRIPTIONS: Record<Granularity, string> = {
  快速: "少量追问，适合需求已经明确时使用。",
  标准: "补齐教学目标和重点，适合日常备课。",
  精细: "更充分地讨论教学方法与互动，适合打磨一节课。",
};
export const MODES: Granularity[] = ["快速", "标准", "精细"];
