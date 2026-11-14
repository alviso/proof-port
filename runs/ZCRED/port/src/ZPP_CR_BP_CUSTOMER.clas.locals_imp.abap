CLASS lhc_customer DEFINITION INHERITING FROM cl_abap_behavior_handler.

  PRIVATE SECTION.

    CONSTANTS:
      c_blocked  TYPE zcr_customer-blocked  VALUE 'X',
      c_priority TYPE zcr_customer-priority VALUE 'V'.

    " screen 0200 PBO, MODULE lock_priority: the new limit is display only for a priority customer
    METHODS get_instance_features FOR INSTANCE FEATURES
      IMPORTING keys REQUEST requested_features FOR Customer RESULT result.

    " screen 0100 PAI, MODULE check_customer
    METHODS choosecustomer FOR MODIFY
      IMPORTING keys FOR ACTION Customer~ChooseCustomer.

    " screen 0200 PAI with function code SAVE
    METHODS changecreditlimit FOR MODIFY
      IMPORTING keys FOR ACTION Customer~ChangeCreditLimit.

    " FORM save_change: IF gv_new_limit = 0. gs_cust-blocked = 'X'. ENDIF.
    METHODS blockwhenzero FOR DETERMINE ON MODIFY
      IMPORTING keys FOR Customer~blockWhenZero.

    " MODULE check_change, in the old order
    METHODS checkchange FOR VALIDATE ON SAVE
      IMPORTING keys FOR Customer~checkChange.

ENDCLASS.

CLASS lhc_customer IMPLEMENTATION.

  METHOD get_instance_features.

    READ ENTITIES OF zpp_cr_c_customer IN LOCAL MODE
      ENTITY Customer
        FIELDS ( Priority )
        WITH CORRESPONDING #( keys )
      RESULT DATA(lt_customer).

    result = VALUE #( FOR ls_customer IN lt_customer
                      ( Customer           = ls_customer-Customer
                        %field-CreditLimit = COND #( WHEN ls_customer-Priority = c_priority
                                                     THEN if_abap_behv=>fc-f-read_only
                                                     ELSE if_abap_behv=>fc-f-unrestricted ) ) ).

  ENDMETHOD.

  METHOD choosecustomer.

    DATA ls_customer TYPE zcr_customer.

    LOOP AT keys INTO DATA(ls_key).

      CLEAR ls_customer.
      SELECT SINGLE * FROM zcr_customer
        WHERE kunnr = @ls_key-%param-Customer
        INTO @ls_customer.

      IF sy-subrc <> 0.
        APPEND VALUE #( %cid = ls_key-%cid ) TO failed-customer.
        APPEND VALUE #( %cid = ls_key-%cid
                        %msg = new_message_with_text(
                                 severity = if_abap_behv_message=>severity-error
                                 text     = 'Customer not found' ) ) TO reported-customer.
        CONTINUE.
      ENDIF.

      IF ls_customer-blocked = c_blocked.
        APPEND VALUE #( %cid = ls_key-%cid ) TO failed-customer.
        APPEND VALUE #( %cid = ls_key-%cid
                        %msg = new_message_with_text(
                                 severity = if_abap_behv_message=>severity-error
                                 text     = 'Customer is blocked' ) ) TO reported-customer.
      ENDIF.

    ENDLOOP.

  ENDMETHOD.

  METHOD changecreditlimit.

    DATA ls_customer TYPE zcr_customer.
    DATA lv_new      TYPE zcr_customer-credit_limit.

    LOOP AT keys INTO DATA(ls_key).

      CLEAR ls_customer.
      SELECT SINGLE * FROM zcr_customer
        WHERE kunnr = @ls_key-Customer
        INTO @ls_customer.

      IF sy-subrc <> 0.
        APPEND VALUE #( Customer = ls_key-Customer ) TO failed-customer.
        APPEND VALUE #( Customer = ls_key-Customer
                        %msg = new_message_with_text(
                                 severity = if_abap_behv_message=>severity-error
                                 text     = 'Customer not found' ) ) TO reported-customer.
        CONTINUE.
      ENDIF.

      lv_new = ls_key-%param-NewLimit.
      IF ls_customer-priority = c_priority.
        " the field is display only, so it still holds the limit the customer was loaded with
        lv_new = ls_customer-credit_limit.
      ENDIF.

      DELETE zpp_cr_bp_customer=>pending WHERE kunnr = ls_key-Customer.
      INSERT VALUE #( kunnr     = ls_key-Customer
                      waers     = ls_customer-waers
                      old_limit = ls_customer-credit_limit
                      new_limit = lv_new
                      reason    = ls_key-%param-Reason
                      checked   = abap_false ) INTO TABLE zpp_cr_bp_customer=>pending.

      MODIFY ENTITIES OF zpp_cr_c_customer IN LOCAL MODE
        ENTITY Customer
          UPDATE FIELDS ( CreditLimit )
          WITH VALUE #( ( Customer    = ls_key-Customer
                          CreditLimit = lv_new ) )
        FAILED   DATA(ls_failed)
        REPORTED DATA(ls_reported).

      APPEND LINES OF ls_failed-customer   TO failed-customer.
      APPEND LINES OF ls_reported-customer TO reported-customer.

    ENDLOOP.

  ENDMETHOD.

  METHOD blockwhenzero.

    DATA lt_update TYPE TABLE FOR UPDATE zpp_cr_c_customer.

    READ ENTITIES OF zpp_cr_c_customer IN LOCAL MODE
      ENTITY Customer
        FIELDS ( CreditLimit Blocked )
        WITH CORRESPONDING #( keys )
      RESULT DATA(lt_customer).

    LOOP AT lt_customer INTO DATA(ls_customer).
      IF ls_customer-CreditLimit = 0 AND ls_customer-Blocked <> c_blocked.
        APPEND VALUE #( Customer = ls_customer-Customer
                        Blocked  = c_blocked ) TO lt_update.
      ENDIF.
    ENDLOOP.

    IF lt_update IS NOT INITIAL.
      MODIFY ENTITIES OF zpp_cr_c_customer IN LOCAL MODE
        ENTITY Customer
          UPDATE FIELDS ( Blocked )
          WITH lt_update
        REPORTED DATA(ls_reported).
    ENDIF.

  ENDMETHOD.

  METHOD checkchange.

    DATA ls_db        TYPE zcr_customer.
    DATA lv_threshold TYPE zcr_limit_rule-threshold.
    DATA lv_reason    TYPE zcr_changelog-reason.
    DATA lv_text      TYPE string.

    READ ENTITIES OF zpp_cr_c_customer IN LOCAL MODE
      ENTITY Customer
        FIELDS ( CreditLimit )
        WITH CORRESPONDING #( keys )
      RESULT DATA(lt_customer).

    LOOP AT lt_customer INTO DATA(ls_customer).

      CLEAR: ls_db, lv_threshold, lv_reason, lv_text.

      READ TABLE zpp_cr_bp_customer=>pending WITH KEY kunnr = ls_customer-Customer
        INTO DATA(ls_pending).
      IF sy-subrc = 0.
        lv_reason = ls_pending-reason.
      ENDIF.

      SELECT SINGLE * FROM zcr_customer
        WHERE kunnr = @ls_customer-Customer
        INTO @ls_db.

      IF sy-subrc <> 0.
        lv_text = 'Customer not found'.
      ELSEIF ls_db-blocked = c_blocked.
        lv_text = 'Customer is blocked'.
      ELSEIF ls_customer-CreditLimit < 0.
        lv_text = 'Credit limit cannot be negative'.
      ELSEIF ls_customer-CreditLimit = ls_db-credit_limit.
        lv_text = 'Credit limit is unchanged'.
      ELSE.
        SELECT SINGLE threshold FROM zcr_limit_rule
          WHERE waers = @ls_db-waers
          INTO @lv_threshold.
        IF ls_customer-CreditLimit > lv_threshold AND lv_reason IS INITIAL.
          lv_text = 'A reason is required for this limit'.
        ENDIF.
      ENDIF.

      IF lv_text IS NOT INITIAL.
        APPEND VALUE #( Customer = ls_customer-Customer ) TO failed-customer.
        APPEND VALUE #( Customer = ls_customer-Customer
                        %msg = new_message_with_text(
                                 severity = if_abap_behv_message=>severity-error
                                 text     = lv_text ) ) TO reported-customer.
        CONTINUE.
      ENDIF.

      " the change passed every check: hand the log row's values to the additional save
      READ TABLE zpp_cr_bp_customer=>pending WITH KEY kunnr = ls_customer-Customer
        ASSIGNING FIELD-SYMBOL(<ls_pending>).
      IF sy-subrc = 0.
        <ls_pending>-waers     = ls_db-waers.
        <ls_pending>-old_limit = ls_db-credit_limit.
        <ls_pending>-new_limit = ls_customer-CreditLimit.
        <ls_pending>-checked   = abap_true.
      ELSE.
        INSERT VALUE #( kunnr     = ls_customer-Customer
                        waers     = ls_db-waers
                        old_limit = ls_db-credit_limit
                        new_limit = ls_customer-CreditLimit
                        reason    = lv_reason
                        checked   = abap_true ) INTO TABLE zpp_cr_bp_customer=>pending.
      ENDIF.

    ENDLOOP.

  ENDMETHOD.

ENDCLASS.


CLASS lsc_zpp_cr_c_customer DEFINITION INHERITING FROM cl_abap_behavior_saver.

  PROTECTED SECTION.

    " FORM save_change: INSERT zcr_changelog FROM ls_log
    METHODS save_modified REDEFINITION.
    METHODS cleanup_finalize REDEFINITION.

ENDCLASS.

CLASS lsc_zpp_cr_c_customer IMPLEMENTATION.

  METHOD save_modified.

    DATA ls_log TYPE zcr_changelog.

    LOOP AT update-customer INTO DATA(ls_update).

      READ TABLE zpp_cr_bp_customer=>pending WITH KEY kunnr = ls_update-Customer
        INTO DATA(ls_pending).
      IF sy-subrc <> 0 OR ls_pending-checked = abap_false.
        CONTINUE.
      ENDIF.

      CLEAR ls_log.
      GET TIME STAMP FIELD ls_log-changed_at.
      ls_log-kunnr     = ls_pending-kunnr.
      ls_log-waers     = ls_pending-waers.
      ls_log-old_limit = ls_pending-old_limit.
      ls_log-new_limit = ls_pending-new_limit.
      ls_log-uname     = sy-uname.
      ls_log-reason    = ls_pending-reason.

      INSERT zcr_changelog FROM @ls_log.

    ENDLOOP.

  ENDMETHOD.

  METHOD cleanup_finalize.

    CLEAR zpp_cr_bp_customer=>pending.

  ENDMETHOD.

ENDCLASS.
