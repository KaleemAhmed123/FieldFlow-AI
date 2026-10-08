// AUTO-GENERATED from packages/contract/schema/AppointmentAtRisk.json — DO NOT EDIT.
// Regenerate with: pnpm run types  (after `make schema` in the repo root).
/* eslint-disable */

export type Eventid = string;
export type Correlationid = string;
export type Event = "appointment.at_risk";
export type Occurredat = string;
export type Appointmentid = string;
export type Workorderid = string;
export type Reason =
  | "technician_delay"
  | "traffic_weather"
  | "technician_no_show"
  | "customer_access_issue"
  | "part_missing"
  | "wrong_part_shipped"
  | "additional_fault_found"
  | "asset_complex"
  | "safety_risk"
  | "warranty_dispute";

export interface AppointmentAtRisk {
  eventId?: Eventid;
  correlationId: Correlationid;
  event?: Event;
  occurredAt?: Occurredat;
  appointmentId: Appointmentid;
  workOrderId: Workorderid;
  reason?: Reason;
  detail?: Detail;
}
export interface Detail {
  [k: string]: unknown;
}
