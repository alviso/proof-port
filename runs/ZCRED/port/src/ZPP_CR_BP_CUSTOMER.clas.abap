CLASS zpp_cr_bp_customer DEFINITION
  PUBLIC
  ABSTRACT
  FINAL
  FOR BEHAVIOR OF zpp_cr_c_customer.

  PUBLIC SECTION.

    " What the old program kept in gs_cust and gv_reason between screen 0200 and FORM save_change.
    " The action fills the reason, the validation fills the values read from the database, and the
    " additional save writes the log row from it.
    TYPES:
      BEGIN OF ty_pending,
        kunnr     TYPE zcr_customer-kunnr,
        waers     TYPE zcr_customer-waers,
        old_limit TYPE zcr_customer-credit_limit,
        new_limit TYPE zcr_customer-credit_limit,
        reason    TYPE zcr_changelog-reason,
        checked   TYPE abap_boolean,
      END OF ty_pending,
      ty_pending_tab TYPE SORTED TABLE OF ty_pending WITH UNIQUE KEY kunnr.

    CLASS-DATA pending TYPE ty_pending_tab.

ENDCLASS.

CLASS zpp_cr_bp_customer IMPLEMENTATION.
ENDCLASS.
