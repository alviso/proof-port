PROGRAM sapmzcred.

DATA: ok_code      TYPE sy-ucomm,
      gv_kunnr     TYPE c LENGTH 10,
      gv_name1     TYPE c LENGTH 35,
      gv_waers     TYPE c LENGTH 5,
      gv_old_limit TYPE p LENGTH 8 DECIMALS 2,
      gv_new_limit TYPE p LENGTH 8 DECIMALS 2,
      gv_reason    TYPE c LENGTH 60,
      gs_cust      TYPE zcr_customer.

MODULE status_main OUTPUT.
  SET PF-STATUS 'ZMAIN'.
ENDMODULE.

MODULE lock_priority OUTPUT.
  IF gs_cust-priority = 'V'.
    LOOP AT SCREEN.
      IF screen-name = 'GV_NEW_LIMIT'.
        screen-input = 0.
        MODIFY SCREEN.
      ENDIF.
    ENDLOOP.
  ENDIF.
ENDMODULE.

MODULE exit_command INPUT.
  LEAVE TO SCREEN 0.
ENDMODULE.

MODULE check_customer INPUT.
  SELECT SINGLE * FROM zcr_customer INTO gs_cust
    WHERE kunnr = gv_kunnr.
  IF sy-subrc <> 0.
    MESSAGE 'Customer not found' TYPE 'E'.
  ENDIF.
  IF gs_cust-blocked = 'X'.
    MESSAGE 'Customer is blocked' TYPE 'E'.
  ENDIF.
ENDMODULE.

MODULE f4_customer INPUT.
  PERFORM f4_customer.
ENDMODULE.

MODULE user_command_0100 INPUT.
  CLEAR ok_code.
  gv_name1     = gs_cust-name1.
  gv_waers     = gs_cust-waers.
  gv_old_limit = gs_cust-credit_limit.
  gv_new_limit = gs_cust-credit_limit.
  CLEAR gv_reason.
  LEAVE TO SCREEN 200.
ENDMODULE.

MODULE check_change INPUT.
  DATA lv_threshold TYPE p LENGTH 8 DECIMALS 2.

  CHECK ok_code = 'SAVE'.

  IF gv_new_limit < 0.
    MESSAGE 'Credit limit cannot be negative' TYPE 'E'.
  ENDIF.

  IF gv_new_limit = gs_cust-credit_limit.
    MESSAGE 'Credit limit is unchanged' TYPE 'E'.
  ENDIF.

  CLEAR lv_threshold.
  SELECT SINGLE threshold FROM zcr_limit_rule INTO lv_threshold
    WHERE waers = gs_cust-waers.

  IF gv_new_limit > lv_threshold AND gv_reason IS INITIAL.
    MESSAGE 'A reason is required for this limit' TYPE 'E'.
  ENDIF.
ENDMODULE.

MODULE user_command_0200 INPUT.
  DATA lv_ucomm TYPE sy-ucomm.

  lv_ucomm = ok_code.
  CLEAR ok_code.

  IF lv_ucomm = 'SAVE'.
    PERFORM save_change.
    MESSAGE 'Credit limit changed' TYPE 'S'.
    LEAVE TO SCREEN 0.
  ENDIF.
ENDMODULE.

FORM save_change.
  DATA ls_log TYPE zcr_changelog.

  GET TIME STAMP FIELD ls_log-changed_at.
  ls_log-kunnr     = gs_cust-kunnr.
  ls_log-waers     = gs_cust-waers.
  ls_log-old_limit = gs_cust-credit_limit.
  ls_log-new_limit = gv_new_limit.
  ls_log-uname     = sy-uname.
  ls_log-reason    = gv_reason.

  gs_cust-credit_limit = gv_new_limit.
  IF gv_new_limit = 0.
    gs_cust-blocked = 'X'.
  ENDIF.

  UPDATE zcr_customer FROM gs_cust.
  INSERT zcr_changelog FROM ls_log.
  COMMIT WORK.
ENDFORM.

* F4 on the customer: every customer in ZCR_CUSTOMER, with the column headings the table itself doesn't have.
FORM f4_customer.
  DATA: lt_cust   TYPE STANDARD TABLE OF zcr_customer,
        lt_all    TYPE STANDARD TABLE OF dfies,
        lt_fields TYPE STANDARD TABLE OF dfies,
        ls_field  TYPE dfies.

  SELECT * FROM zcr_customer INTO TABLE @lt_cust ORDER BY kunnr.

  CALL FUNCTION 'DDIF_FIELDINFO_GET'
    EXPORTING
      tabname   = 'ZCR_CUSTOMER'
    TABLES
      dfies_tab = lt_all
    EXCEPTIONS
      OTHERS    = 1.

  LOOP AT lt_all INTO ls_field.
    CASE ls_field-fieldname.
      WHEN 'KUNNR'.
        ls_field-reptext = 'Customer'.
      WHEN 'NAME1'.
        ls_field-reptext = 'Name'.
      WHEN 'WAERS'.
        ls_field-reptext = 'Currency'.
      WHEN 'BLOCKED'.
        ls_field-reptext = 'Blocked'.
      WHEN OTHERS.
        CONTINUE.
    ENDCASE.
    ls_field-scrtext_s = ls_field-reptext.
    ls_field-scrtext_m = ls_field-reptext.
    ls_field-scrtext_l = ls_field-reptext.
    APPEND ls_field TO lt_fields.
  ENDLOOP.

  CALL FUNCTION 'F4IF_INT_TABLE_VALUE_REQUEST'
    EXPORTING
      retfield    = 'KUNNR'
      dynpprog    = sy-repid
      dynpnr      = sy-dynnr
      dynprofield = 'GV_KUNNR'
      value_org   = 'S'
    TABLES
      value_tab   = lt_cust
      field_tab   = lt_fields
    EXCEPTIONS
      OTHERS      = 1.
ENDFORM.