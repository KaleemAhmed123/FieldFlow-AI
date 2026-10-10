/** Copilot tool: open appointments whose asset is OUT of warranty (chargeable parts). READ-ONLY. */
global with sharing class FFCopilot_OutOfWarranty {
    global class Request {
        @InvocableVariable(label='Max results' description='How many to return at most (default 10).')
        global Integer limitCount;
    }
    global class Row {
        @InvocableVariable global String appointmentNumber;
        @InvocableVariable global String status;
        @InvocableVariable global Datetime scheduledStart;
    }

    @InvocableMethod(label='Find out-of-warranty jobs'
        description='List open field-service appointments whose serviced asset is OUT of warranty, so parts are chargeable, soonest first. Use this to find revenue opportunities or jobs that need a paid quote.')
    global static List<Row> run(List<Request> requests) {
        Integer cap = (requests != null && !requests.isEmpty() && requests[0].limitCount != null)
            ? requests[0].limitCount : 10;
        List<ServiceAppointment> openAppts = [SELECT AppointmentNumber, Status, SchedStartTime,
                ParentRecordId FROM ServiceAppointment
                WHERE Status NOT IN ('Completed', 'Cancelled', 'Closed')
                ORDER BY SchedStartTime ASC NULLS LAST LIMIT 200];
        Set<Id> parentIds = new Set<Id>();
        for (ServiceAppointment sa : openAppts) {
            if (sa.ParentRecordId != null) parentIds.add(sa.ParentRecordId);
        }
        Map<Id, Id> woToAsset = new Map<Id, Id>();
        for (WorkOrder wo : [SELECT Id, AssetId FROM WorkOrder WHERE Id IN :parentIds]) {
            if (wo.AssetId != null) woToAsset.put(wo.Id, wo.AssetId);
        }
        Set<Id> expired = new Set<Id>();
        for (Asset a : [SELECT Id FROM Asset
                        WHERE Id IN :woToAsset.values() AND Warranty_Active__c = false]) {
            expired.add(a.Id);
        }
        List<Row> rows = new List<Row>();
        for (ServiceAppointment sa : openAppts) {
            Id assetId = woToAsset.get(sa.ParentRecordId);
            if (assetId != null && expired.contains(assetId)) {
                Row r = new Row();
                r.appointmentNumber = sa.AppointmentNumber;
                r.status = sa.Status;
                r.scheduledStart = sa.SchedStartTime;
                rows.add(r);
                if (rows.size() >= cap) break;
            }
        }
        return rows;
    }
}
