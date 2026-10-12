/**
 * FieldFlow AI — the record trigger that starts a recovery case from inside Salesforce.
 *
 * Fires when a ServiceAppointment *becomes* at-risk, by EITHER signal:
 *   - At_Risk__c flips to true (our explicit "fire it" checkbox), OR
 *   - Status changes to 'Cannot Complete' (the standard Field Service "it failed" state).
 * "Becomes" = we compare to the old value, so a re-save of an already-at-risk record doesn't re-fire.
 *
 * It only COLLECTS the ids and hands them to FieldFlowAtRisk.notify (an @future callout) — a trigger
 * itself can't make an HTTP call. Bulk-safe: one future call for the whole batch, not one per row.
 */
trigger ServiceAppointmentAtRisk on ServiceAppointment (after insert, after update) {
    Set<Id> fired = new Set<Id>();
    for (ServiceAppointment sa : Trigger.new) {
        ServiceAppointment old = Trigger.isUpdate ? Trigger.oldMap.get(sa.Id) : null;
        Boolean checkedNow = sa.At_Risk__c == true && (old == null || old.At_Risk__c != true);
        Boolean failedNow  = sa.Status == 'Cannot Complete'
                             && (old == null || old.Status != 'Cannot Complete');
        if (checkedNow || failedNow) {
            fired.add(sa.Id);
        }
    }
    if (!fired.isEmpty()) {
        FieldFlowAtRisk.notify(fired);
    }
}
