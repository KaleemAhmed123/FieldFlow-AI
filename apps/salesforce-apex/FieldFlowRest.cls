/**
 * FieldFlow AI — the Salesforce read + reschedule surface, as Apex REST.
 *
 * WHY Apex REST (not a hosted-MCP tool): the orchestrator's Toolbox calls this directly over HTTPS,
 * deterministically. The authority ladder ("can this reschedule happen?") lives in our Python, NOT
 * in an LLM-invoked MCP tool — the LLM proposes, policy decides. Hosted MCP (Headless 360) can wrap
 * these same endpoints later if we want that story; this class is the no-regret foundation.
 *
 * Decision A (2026-10-10): inventory left Salesforce. There is deliberately NO part/stock endpoint
 * here — product image/price/stock is the e-com service's job.
 *
 * Base URL once deployed:
 *   https://<yourdomain>.my.salesforce.com/services/apexrest/fieldflow/...
 *   GET  .../appointment/{id}   .../customer/{id}   .../asset/{id}   .../technician/{id}
 *   POST .../reschedule         body: {"appointmentId":"...","startTime":"ISO","endTime":"ISO"}
 *
 * The JSON shapes match app/tools/salesforce.py (FakeSalesforce) so our Python adapter is a thin swap.
 *
 * ⚠ ORG ASSUMPTIONS (confirm / adjust the SOQL to match your demo data chain — see README §4):
 *   A1. Warranty = a custom checkbox Asset.Warranty_Active__c (handoff OQ-A). true→"active".
 *   A2. ServiceAppointment.ParentRecordId points at the WorkOrder; the WorkOrder carries ContactId +
 *       AssetId. The technician is the ServiceResource on the appointment's AssignedResource.
 *   A3. The id we pass is matched against ServiceAppointment.AppointmentNumber OR the 18-char Id.
 *   A4. slaWindowMinutes has no standard field — defaulted to 120 (swap for a custom field if needed).
 */
@RestResource(urlMapping='/fieldflow/*')
global with sharing class FieldFlowRest {
    @HttpGet
    global static void doGet() {
        RestResponse res = RestContext.response;
        res.addHeader('Content-Type', 'application/json');
        List<String> parts = RestContext.request.requestURI.substringAfter('/fieldflow/').split('/');
        String kind = parts.size() > 0 ? parts[0] : '';
        String id = parts.size() > 1 ? EncodingUtil.urlDecode(parts[1], 'UTF-8') : '';
        try {
            Object body =
                kind == 'appointment' ? (Object) getAppointment(id)
              : kind == 'customer'    ? (Object) getCustomer(id)
              : kind == 'asset'       ? (Object) getAsset(id)
              : kind == 'technician'  ? (Object) getTechnician(id)
              : null;
            if (kind != 'appointment' && kind != 'customer' && kind != 'asset' && kind != 'technician') {
                fail(res, 404, 'unknown resource "' + kind + '"');
            } else if (body == null) {
                fail(res, 404, kind + ' "' + id + '" not found');
            } else {
                res.responseBody = Blob.valueOf(JSON.serialize(body));
            }
        } catch (Exception e) {
            fail(res, 500, e.getMessage());  // fail loud — the caller logs the body (golden rule)
        }
    }

    @HttpPost
    global static void doPost() {
        RestResponse res = RestContext.response;
        res.addHeader('Content-Type', 'application/json');
        String path = RestContext.request.requestURI.substringAfter('/fieldflow/');
        try {
            if (!path.startsWith('reschedule')) {
                fail(res, 404, 'unknown action "' + path + '"');
                return;
            }
            Map<String, Object> in =
                (Map<String, Object>) JSON.deserializeUntyped(RestContext.request.requestBody.toString());
            String apptId = (String) in.get('appointmentId');
            ServiceAppointment sa = findAppointment(apptId);
            if (sa == null) { fail(res, 404, 'appointment "' + apptId + '" not found'); return; }
            // The slotId -> start/end mapping is done in our Python adapter (we own the slot catalog),
            // so this endpoint takes concrete times. Direct field update (handoff OQ-D) for the POC.
            sa.SchedStartTime = parseIso((String) in.get('startTime'));
            sa.SchedEndTime = parseIso((String) in.get('endTime'));
            update sa;
            res.responseBody = Blob.valueOf(JSON.serialize(new Map<String, Object>{
                'appointmentId' => apptId, 'status' => 'RESCHEDULED'
            }));
        } catch (Exception e) {
            fail(res, 500, e.getMessage());
        }
    }

    // --- reads (shapes mirror FakeSalesforce) -------------------------------------------------
    static Map<String, Object> getAppointment(String id) {
        ServiceAppointment sa = findAppointment(id);
        if (sa == null) return null;
        Id customerId, assetId, resourceId;
        try {
            WorkOrder wo = [SELECT ContactId, AssetId FROM WorkOrder WHERE Id = :sa.ParentRecordId LIMIT 1];
            customerId = wo.ContactId;
            assetId = wo.AssetId;
        } catch (Exception ignore) { /* Parent isn't a WorkOrder in this org — leave null (A2) */ }
        for (AssignedResource ar : [SELECT ServiceResourceId FROM AssignedResource
                                    WHERE ServiceAppointmentId = :sa.Id LIMIT 1]) {
            resourceId = ar.ServiceResourceId;
        }
        return new Map<String, Object>{
            'appointmentId' => sa.AppointmentNumber,
            'customerId' => customerId,
            'assetId' => assetId,
            'resourceId' => resourceId,
            'slaWindowMinutes' => 120,            // A4
            'caseState' => sa.Status
        };
    }

    static Map<String, Object> getCustomer(String id) {
        for (Contact c : [SELECT Name, Phone, MobilePhone FROM Contact WHERE Id = :id LIMIT 1]) {
            return new Map<String, Object>{
                'name' => c.Name, 'phone' => c.MobilePhone != null ? c.MobilePhone : c.Phone
            };
        }
        return null;
    }

    static Map<String, Object> getAsset(String id) {
        for (Asset a : [SELECT Name, Warranty_Active__c FROM Asset WHERE Id = :id LIMIT 1]) {  // A1
            return new Map<String, Object>{
                'model' => a.Name, 'warranty' => a.Warranty_Active__c ? 'active' : 'expired'
            };
        }
        return null;
    }

    static Map<String, Object> getTechnician(String id) {
        List<ServiceResource> rows = [SELECT Name FROM ServiceResource WHERE Id = :id LIMIT 1];
        if (rows.isEmpty()) return null;
        List<String> skills = new List<String>();
        for (ServiceResourceSkill s : [SELECT Skill.MasterLabel FROM ServiceResourceSkill
                                       WHERE ServiceResourceId = :id]) {
            skills.add(s.Skill.MasterLabel);
        }
        String territory;
        for (ServiceTerritoryMember m : [SELECT ServiceTerritory.Name FROM ServiceTerritoryMember
                                         WHERE ServiceResourceId = :id LIMIT 1]) {
            territory = m.ServiceTerritory.Name;
        }
        return new Map<String, Object>{
            'name' => rows[0].Name, 'skills' => skills, 'territory' => territory
        };
    }

    // --- helpers ------------------------------------------------------------------------------
    static ServiceAppointment findAppointment(String id) {
        List<ServiceAppointment> rows = [
            SELECT Id, AppointmentNumber, Status, ParentRecordId, SchedStartTime, SchedEndTime
            FROM ServiceAppointment
            WHERE AppointmentNumber = :id OR Id = :id LIMIT 1   // A3
        ];
        return rows.isEmpty() ? null : rows[0];
    }

    static Datetime parseIso(String iso) {
        // Accept "2026-10-12T14:00:00Z" or with offset; Apex JSON gives a parseable datetime string.
        return (Datetime) JSON.deserialize('"' + iso + '"', Datetime.class);
    }

    static void fail(RestResponse res, Integer code, String msg) {
        res.statusCode = code;
        res.responseBody = Blob.valueOf(JSON.serialize(new Map<String, Object>{ 'error' => msg }));
    }
}
