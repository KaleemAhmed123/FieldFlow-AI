// AUTO-GENERATED from packages/contract/schema/CaseView.json — DO NOT EDIT.
// Regenerate with: pnpm run types  (after `make schema` in the repo root).
/* eslint-disable */

export type Correlationid = string;
export type Status = string;
export type Kind = string;
export type Title = string;
export type Body = string;
export type Slotid = string;
export type Label = string;
export type Technician = string;
export type Note = string;
export type Options = SlotOption[];
export type Type = string;
export type Label1 = string;
export type Value = string;
export type Actions = CardAction[];
export type Payurl = string | null;
export type Version = number;
export type Updatedat = string;

/**
 * What the control panel shows per recovery case.
 */
export interface CaseView {
  correlationId: Correlationid;
  status: Status;
  context?: Context;
  decisionTrace?: Decisiontrace;
  sentCard?: Card | null;
  updatedAt: Updatedat;
}
export interface Context {
  [k: string]: unknown;
}
export interface Decisiontrace {
  [k: string]: unknown;
}
/**
 * A minimal RCS-card-ish payload. FakeVonage 'sends' this; real Vonage renders it later.
 */
export interface Card {
  kind: Kind;
  title: Title;
  body?: Body;
  options?: Options;
  actions?: Actions;
  payUrl?: Payurl;
  version?: Version;
}
export interface SlotOption {
  slotId: Slotid;
  label: Label;
  technician: Technician;
  note?: Note;
}
/**
 * A suggested action chip on a card (slice 2). `type` maps to a real RCS suggested action:
 * share_location (customer sends GPS), dial (call a number), calendar (add the appointment),
 * view (open a URL). `value` carries the phone/url/label the action needs; blank where unused.
 */
export interface CardAction {
  type: Type;
  label: Label1;
  value?: Value;
}
