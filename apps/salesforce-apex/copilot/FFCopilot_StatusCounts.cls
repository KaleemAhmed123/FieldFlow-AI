/** Copilot tool: appointment counts grouped by status (a quick pulse). READ-ONLY. */
global with sharing class FFCopilot_StatusCounts {
    global class Request {
        @InvocableVariable(label='(unused)' description='No input needed; leave blank.')
        global String ignore;
    }
    global class StatusCount {
        @InvocableVariable global String status;
        @InvocableVariable global Integer total;
    }

    @InvocableMethod(label='Count appointments by status'
        description='Return how many field-service appointments are in each status, a quick pulse of the whole queue. Use this to answer how many jobs are open versus completed or for a breakdown by status.')
    global static List<StatusCount> run(List<Request> requests) {
        List<StatusCount> out = new List<StatusCount>();
        for (AggregateResult ar : [SELECT Status, COUNT(Id) total
                FROM ServiceAppointment GROUP BY Status]) {
            StatusCount sc = new StatusCount();
            sc.status = (String) ar.get('Status');
            sc.total = (Integer) ar.get('total');
            out.add(sc);
        }
        return out;
    }
}
