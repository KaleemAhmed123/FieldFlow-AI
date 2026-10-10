/** Copilot tool: an asset's service history (by Asset name or Id). READ-ONLY. */
global with sharing class FFCopilot_AssetHistory {
    global class Request {
        @InvocableVariable(required=true label='Asset name or Id'
            description='An Asset name (e.g. the product model) or its 18-char Asset Id.')
        global String asset;
    }
    global class Row {
        @InvocableVariable global String appointmentNumber;
        @InvocableVariable global String status;
        @InvocableVariable global Datetime scheduledStart;
    }

    @InvocableMethod(label='Get asset service history'
        description='List all field-service appointments for a given asset or product (by Asset name or Id), most recent first. Use this to answer how many times an asset has been serviced or to review its service history.')
    global static List<Row> run(List<Request> requests) {
        List<Row> rows = new List<Row>();
        for (Request req : requests) {
            Id assetId = null;
            try { assetId = (Id) req.asset; } catch (Exception e) { /* it's a name */ }
            if (assetId == null) {
                List<Asset> found = [SELECT Id FROM Asset WHERE Name = :req.asset LIMIT 1];
                if (!found.isEmpty()) assetId = found[0].Id;
            }
            if (assetId == null) continue;
            List<Id> woIds = new List<Id>();
            for (WorkOrder wo : [SELECT Id FROM WorkOrder WHERE AssetId = :assetId]) {
                woIds.add(wo.Id);
            }
            for (ServiceAppointment sa : [SELECT AppointmentNumber, Status, SchedStartTime
                    FROM ServiceAppointment WHERE ParentRecordId IN :woIds
                    ORDER BY SchedStartTime DESC NULLS LAST LIMIT 50]) {
                Row r = new Row();
                r.appointmentNumber = sa.AppointmentNumber;
                r.status = sa.Status;
                r.scheduledStart = sa.SchedStartTime;
                rows.add(r);
            }
        }
        return rows;
    }
}
