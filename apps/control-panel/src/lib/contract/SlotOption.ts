// AUTO-GENERATED from packages/contract/schema/SlotOption.json — DO NOT EDIT.
// Regenerate with: pnpm run types  (after `make schema` in the repo root).
/* eslint-disable */

export type Slotid = string;
export type Label = string;
export type Technician = string;
export type Note = string;

export interface SlotOption {
  slotId: Slotid;
  label: Label;
  technician: Technician;
  note?: Note;
}
