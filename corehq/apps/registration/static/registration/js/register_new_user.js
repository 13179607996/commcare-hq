$(function () {
    var initial_page_data = hqImport('hqwebapp/js/initial_page_data.js').get;

    $(window).on('resize load', function () {
        var newHeight = $(window).height() - $('#hq-navigation').outerHeight() - $('#hq-footer').outerHeight() - 1;  // -1 for rounding errors
        var minHeight = initial_page_data('show_number') ? 600 : 450;
        $('.reg-form-column').css('min-height', Math.max(newHeight, minHeight) + 'px');
    });

    var reg = hqImport('registration/js/new_user.ko.js');
    reg.onModuleLoad = function () {
        $('.loading-form-step').fadeOut(500, function () {
            $('.step-1').fadeIn(500);
        });
    };
    reg.initRMI(hqImport('hqwebapp/js/urllib.js').reverse('process_registration'));
    if (!initial_page_data('hide_password_feedback')) {
        reg.showPasswordFeedback();
    }
    var regForm = new reg.FormViewModel(
        initial_page_data('reg_form_defaults'),
        '#registration-form-container',
        ['step-1', 'step-2', 'final-step']
    );
    $('#registration-form-container').koApplyBindings(regForm);

    reg.setResetEmailFeedbackFn(function (isValidating) {
        // separating form and function
        if (isValidating) {
            $('#div_id_email').removeClass('has-error has-success')
                              .addClass('has-warning')
                              .find('.form-control-feedback').removeClass('fa-check fa-remove')
                                                             .addClass('fa-spinner fa-spin');
        } else {
            $('#div_id_email').removeClass('has-warning')
                              .addClass((regForm.emailDelayed.isValid() && regForm.email.isValid()) ? 'has-success' : 'has-error')
                              .find('.form-control-feedback').removeClass('fa-spinner fa-spin')
                              .addClass((regForm.emailDelayed.isValid() && regForm.email.isValid()) ? 'fa-check' : 'fa-remove');
        }
    });

    reg.setSubmitAttemptFn(function () {
        _kmq.push(["trackClick", "create_account_clicked", "Clicked Create Account"]);
    });
    reg.setSubmitSuccessFn(function () {
        _kmq.push(["trackClick", "create_account_success", "Account Creation was Successful"]);
    });

    if (initial_page_data('show_number')) {
        var $number = $('#id_phone_number');
        $number.intlTelInput({
            nationalMode: true,
            utilsScript: initial_page_data('number_utils_script'),
        });
        $number.keydown(function (e) {
            // prevents non-numeric numbers from being entered.
            // from http://stackoverflow.com/questions/995183/how-to-allow-only-numeric-0-9-in-html-inputbox-using-jquery
            // Allow: backspace, delete, tab, escape, enter and .
            if ($.inArray(e.keyCode, [46, 8, 9, 27, 13, 110, 190]) !== -1 ||
                // Allow: Ctrl+A, Command+A
                (e.keyCode === 65 && (e.ctrlKey === true || e.metaKey === true)) ||
                // Allow: home, end, left, right, down, up
                (e.keyCode >= 35 && e.keyCode <= 40)
            ) {
                   // let it happen, don't do anything
                   return;
            }

            // Ensure that it is a number and stop the keypress
            if ((e.shiftKey || (e.keyCode < 48 || e.keyCode > 57)) && (e.keyCode < 96 || e.keyCode > 105)) {
                e.preventDefault();
            }
        });
        reg.setGetPhoneNumberFn(function () {
            var phoneNumber = $number.intlTelInput("getNumber");
            if (phoneNumber) {
                _kmq.push(["trackClick", "submitted_phone_number", "Phone Number Field Filled Out"]);
            }
            return phoneNumber;
        });
    }

    // A/B test setup
    var ab_test = hqImport('hqwebapp/js/initial_page_data.js').get('ab_test');
    if (ab_test) {
        var options = {};
        options[ab_test.name] = ab_test.version;
        _kmq.push(["set", options]);
    }
});
