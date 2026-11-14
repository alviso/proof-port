*"* Behaviour pool of ZPP_MM_R_ARTICLE: the checks and the derived values of the
*"* old ZMM01 module pool.
*"*
*"* Where each old rule lives now:
*"*   MODULE check_0210 (name, type, default base UoM)  -> prepareSave + checkArticle
*"*   MODULE check_0220 (price, default currency)       -> prepareSave + checkArticle
*"*   FORM   check_all  (all of them, then the variants) -> checkArticle
*"*   FORM   save_article (variant currency, header EAN,
*"*          created by/on, changed by/on)              -> prepareSave

CLASS lhc_article DEFINITION INHERITING FROM cl_abap_behavior_handler.

  PRIVATE SECTION.

    METHODS get_global_authorizations FOR GLOBAL AUTHORIZATION
      IMPORTING REQUEST requested_authorizations FOR article RESULT result.

    METHODS preparesave FOR DETERMINE ON MODIFY
      IMPORTING keys FOR article~preparesave.

    METHODS checkarticle FOR VALIDATE ON SAVE
      IMPORTING keys FOR article~checkarticle.

    METHODS presssave FOR MODIFY
      IMPORTING keys FOR ACTION article~presssave.

ENDCLASS.


CLASS lhc_article IMPLEMENTATION.

  METHOD get_global_authorizations.
    IF requested_authorizations-%create = if_abap_behv=>mk-on.
      result-%create = if_abap_behv=>auth-allowed.
    ENDIF.
    IF requested_authorizations-%update = if_abap_behv=>mk-on.
      result-%update = if_abap_behv=>auth-allowed.
    ENDIF.
    IF requested_authorizations-%delete = if_abap_behv=>mk-on.
      result-%delete = if_abap_behv=>auth-allowed.
    ENDIF.
  ENDMETHOD.


  METHOD preparesave.

    DATA lt_variant_upd TYPE TABLE FOR UPDATE zpp_mm_r_article\\variant.

    READ ENTITIES OF zpp_mm_r_article IN LOCAL MODE
      ENTITY article
        ALL FIELDS WITH CORRESPONDING #( keys )
        RESULT DATA(lt_article).

    LOOP AT lt_article INTO DATA(ls_article).

      READ ENTITIES OF zpp_mm_r_article IN LOCAL MODE
        ENTITY article BY \_variant
          ALL FIELDS WITH VALUE #( ( %tky = ls_article-%tky ) )
          RESULT DATA(lt_variant).
      SORT lt_variant BY screenrow variantid.

      " MODULE check_0210 / check_0220: only the subscreen that was open when Save
      " was pressed fills in its own default. Saving from another tab leaves the
      " field as the user left it, empty included.
      DATA(lv_base_uom) = ls_article-baseuom.
      DATA(lv_currency) = ls_article-currency.
      IF ls_article-savetab = 'TAB1' AND lv_base_uom IS INITIAL.
        lv_base_uom = 'ST'.
      ENDIF.
      IF ls_article-savetab = 'TAB2' AND lv_currency IS INITIAL.
        lv_currency = 'EUR'.
      ENDIF.

      " FORM save_article: a variant with no currency of its own takes the header's.
      CLEAR lt_variant_upd.
      LOOP AT lt_variant INTO DATA(ls_variant) WHERE currency IS INITIAL.
        APPEND VALUE #( %tky     = ls_variant-%tky
                        currency = lv_currency ) TO lt_variant_upd.
      ENDLOOP.
      IF lt_variant_upd IS NOT INITIAL.
        MODIFY ENTITIES OF zpp_mm_r_article IN LOCAL MODE
          ENTITY variant
            UPDATE FIELDS ( currency ) WITH lt_variant_upd
          REPORTED DATA(lt_ignore_variant).
      ENDIF.

      " FORM save_article: the header EAN is the EAN of the first variant that has
      " one, in row order; without such a variant the header keeps none. The old
      " program re-derives it on every save, because the screen structure carries
      " no EAN of its own.
      DATA lv_ean TYPE zret_t_article-ean.
      CLEAR lv_ean.
      LOOP AT lt_variant INTO ls_variant.
        IF ls_variant-variantid IS NOT INITIAL AND ls_variant-ean IS NOT INITIAL.
          lv_ean = ls_variant-ean.
          EXIT.
        ENDIF.
      ENDLOOP.

      " FORM save_article: created by/on survive a change, changed by/on are always
      " stamped.
      DATA(lv_created_by) = ls_article-createdby.
      DATA(lv_created_on) = ls_article-createdon.
      IF lv_created_by IS INITIAL AND lv_created_on IS INITIAL.
        lv_created_by = sy-uname.
        lv_created_on = sy-datum.
      ENDIF.

      MODIFY ENTITIES OF zpp_mm_r_article IN LOCAL MODE
        ENTITY article
          UPDATE FIELDS ( baseuom currency ean createdby createdon changedby changedon )
          WITH VALUE #( ( %tky      = ls_article-%tky
                          baseuom   = lv_base_uom
                          currency  = lv_currency
                          ean       = lv_ean
                          createdby = lv_created_by
                          createdon = lv_created_on
                          changedby = sy-uname
                          changedon = sy-datum ) )
        REPORTED DATA(lt_ignore_article).

    ENDLOOP.

  ENDMETHOD.


  METHOD checkarticle.

    READ ENTITIES OF zpp_mm_r_article IN LOCAL MODE
      ENTITY article
        ALL FIELDS WITH CORRESPONDING #( keys )
        RESULT DATA(lt_article).

    LOOP AT lt_article INTO DATA(ls_article).

      READ ENTITIES OF zpp_mm_r_article IN LOCAL MODE
        ENTITY article BY \_variant
          ALL FIELDS WITH VALUE #( ( %tky = ls_article-%tky ) )
          RESULT DATA(lt_variant).
      SORT lt_variant BY screenrow variantid.

      DATA lv_text TYPE string.
      CLEAR lv_text.

      " The open subscreen's own PAI module runs before FORM check_all, so saving
      " from the price tab reports a bad price before a missing name. From the
      " other two tabs check_all alone decides, and its order is name, type,
      " price, then the variants row by row.
      IF ls_article-savetab = 'TAB2' AND ls_article-price <= 0.
        lv_text = 'Le prix doit être supérieur à zéro'.
      ENDIF.
      IF lv_text IS INITIAL AND ls_article-articlename IS INITIAL.
        lv_text = 'Renseignez le nom de l''article'.
      ENDIF.
      IF lv_text IS INITIAL AND ls_article-articletype IS INITIAL.
        lv_text = 'Choisissez un type d''article'.
      ENDIF.
      IF lv_text IS INITIAL AND ls_article-price <= 0.
        lv_text = 'Le prix doit être supérieur à zéro'.
      ENDIF.

      IF lv_text IS INITIAL.
        LOOP AT lt_variant INTO DATA(ls_variant).
          " A row the user never touched is not a variant at all; the old loop
          " skips any row without an identifier and without an EAN.
          IF ls_variant-variantid IS INITIAL AND ls_variant-ean IS INITIAL.
            CONTINUE.
          ENDIF.
          DATA(lv_row) = COND i( WHEN ls_variant-screenrow > 0
                                 THEN ls_variant-screenrow
                                 ELSE sy-tabix ).
          IF ls_variant-variantid IS INITIAL.
            lv_text = |Variante ligne { lv_row } : identifiant manquant|.
            EXIT.
          ENDIF.
          IF ls_variant-ean IS NOT INITIAL
             AND ( strlen( ls_variant-ean ) <> 13 OR ls_variant-ean(13) CN '0123456789' ).
            lv_text = |Variante ligne { lv_row } : l'EAN doit avoir 13 chiffres|.
            EXIT.
          ENDIF.
        ENDLOOP.
      ENDIF.

      " The old screen stops at its first MESSAGE ... TYPE 'E', so exactly one
      " message comes back.
      IF lv_text IS NOT INITIAL.
        APPEND VALUE #( %tky = ls_article-%tky ) TO failed-article.
        APPEND VALUE #( %tky = ls_article-%tky
                        %msg = new_message_with_text(
                                 severity = if_abap_behv_message=>severity-error
                                 text     = lv_text ) ) TO reported-article.
      ENDIF.

    ENDLOOP.

  ENDMETHOD.


  METHOD presssave.

    DATA lt_create TYPE TABLE FOR CREATE zpp_mm_r_article.
    DATA lt_by_variant TYPE TABLE FOR CREATE zpp_mm_r_article\_variant.

    LOOP AT keys INTO DATA(ls_key).

      DATA(ls_in) = ls_key-%param.
      DATA(lv_cid) = |ART{ sy-tabix }|.

      APPEND VALUE #( %cid             = lv_cid
                      articleid        = ls_in-articleid
                      articlename      = ls_in-articlename
                      articletype      = ls_in-articletype
                      baseuom          = ls_in-baseuom
                      activeflag       = ls_in-activeflag
                      price            = ls_in-price
                      currency         = ls_in-currency
                      genericarticleid = ls_in-genericarticleid
                      savetab          = ls_in-savetab ) TO lt_create.

      DATA ls_by_variant LIKE LINE OF lt_by_variant.
      CLEAR ls_by_variant.
      ls_by_variant-%cid_ref  = lv_cid.
      ls_by_variant-articleid = ls_in-articleid.

      " The six lines of the table control. A line with neither an identifier nor
      " an EAN is a line nobody filled in, and the old program steps over it
      " without a word; a line with only a colour or a size on it goes the same way.
      DO 6 TIMES.
        DATA(lv_row) = sy-index.
        ASSIGN COMPONENT |ROW{ lv_row }VARIANTID| OF STRUCTURE ls_in TO FIELD-SYMBOL(<lv_id>).
        ASSIGN COMPONENT |ROW{ lv_row }COLOR|     OF STRUCTURE ls_in TO FIELD-SYMBOL(<lv_color>).
        ASSIGN COMPONENT |ROW{ lv_row }SIZECODE|  OF STRUCTURE ls_in TO FIELD-SYMBOL(<lv_size>).
        ASSIGN COMPONENT |ROW{ lv_row }EAN|       OF STRUCTURE ls_in TO FIELD-SYMBOL(<lv_ean>).
        ASSIGN COMPONENT |ROW{ lv_row }PRICE|     OF STRUCTURE ls_in TO FIELD-SYMBOL(<lv_price>).
        IF <lv_id> IS INITIAL AND <lv_ean> IS INITIAL.
          CONTINUE.
        ENDIF.
        APPEND VALUE #( %cid      = |{ lv_cid }V{ lv_row }|
                        variantid = <lv_id>
                        color     = <lv_color>
                        sizecode  = <lv_size>
                        ean       = <lv_ean>
                        price     = <lv_price>
                        screenrow = lv_row ) TO ls_by_variant-%target.
      ENDDO.

      APPEND ls_by_variant TO lt_by_variant.

    ENDLOOP.

    MODIFY ENTITIES OF zpp_mm_r_article IN LOCAL MODE
      ENTITY article
        CREATE FIELDS ( articleid articlename articletype baseuom activeflag
                        price currency genericarticleid savetab )
          WITH lt_create
      ENTITY article
        CREATE BY \_variant
          FIELDS ( variantid color sizecode ean price screenrow )
          WITH lt_by_variant
      FAILED   DATA(lt_failed)
      REPORTED DATA(lt_reported).

    " Whatever the create and the checks had to say is what the caller hears.
    failed   = CORRESPONDING #( DEEP lt_failed ).
    reported = CORRESPONDING #( DEEP lt_reported ).

  ENDMETHOD.

ENDCLASS.
