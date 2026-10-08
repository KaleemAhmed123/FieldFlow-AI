// AUTO-GENERATED from packages/contract/schema/Card.json — DO NOT EDIT.
// Regenerate with: pnpm run types  (after `make schema` in the repo root).
/* eslint-disable */

export type Kind = string;
export type Title = string;
export type Slotid = string;
export type Label = string;
export type Technician = string;
export type Note = string;
export type Options = SlotOption[];
export type Payurl = string | null;

/**
 * A minimal RCS-card-ish payload. FakeVonage 'sends' this; real Vonage renders it later.
 */
export interface Card {
  kind: Kind;
  title: Title;
  options?: Options;
  payUrl?: Payurl;
}
export interface SlotOption {
  slotId: Slotid;
  label: Label;
  technician: Technician;
  note?: Note;
}
