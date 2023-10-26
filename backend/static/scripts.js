function initializeTabCapture(textareaId) {
    var textarea = document.getElementById(textareaId);

    if (textarea) {
        textarea.addEventListener('keydown', function (e) {
            if (e.key === 'Tab') {
                e.preventDefault(); // Prevent the default tab behavior
                var start = this.selectionStart;
                var end = this.selectionEnd;

                // Insert a tab character at the current cursor position
                this.value = this.value.substring(0, start) + '\t' + this.value.substring(end);

                // Set the cursor position after the inserted tab
                this.selectionStart = this.selectionEnd = start + 1;
            }
        });
    }
}

function lockRuleForModification(rule_id) {
    var postData = {
        rid: rule_id,
    };

    $.ajax({
        type: 'POST', // HTTP method
        url: `/lock_rule/${rule_id}`, // URL to which the request will be sent
        data: postData, // Data to be sent (if needed)
        success: function (response) {
            // Handle the success response here
            console.log(response);
            if (response["success"]) {
                alert(`Lock acquired. Lock expires on ${response["expires_on"]}`)
                window.location.href = `/rule/${rule_id}`
            } else {
                alert(`Failed to acquire lock!\nCurrent lock is held by ${response["locked_by"]}\nLock expires on ${response["expires_on"]}`)
            }
        },
        error: function (error) {
            // Handle any errors here
            console.error(error);
        }
    });
}

function forceUnlockRuleForModification(rule_id) {
    var postData = {
        rid: rule_id,
    };

    $.ajax({
        type: 'POST', // HTTP method
        url: `/unlock/${rule_id}`, // URL to which the request will be sent
        data: postData, // Data to be sent (if needed)
        success: function (response) {
            // Handle the success response here
            window.location.href = `/rule/${rule_id}`
        },
        error: function (error) {
            // Handle any errors here
            console.error(error);
        }
    });
}

function verifyRule(rule_source) {
    return new Promise(function (resolve, reject) {
        var postData = {
            rule_source: rule_source,
        };

        $.ajax({
            type: 'POST',
            url: `/verify_rule`,
            data: JSON.stringify(postData),
            contentType: "application/json",
            success: function (response) {
                resolve(response.params);
            },
            error: function (error) {
                reject(error);
            }
        });
    });
}

function setSampleJson(params, text_area_id) {
    console.log(params)
    $(text_area_id).show();
    let json = ["{"]
    json.push(...params.map(function (s) {
        return `\t"${s}": ,`;
    }))
    json.push("}")
    console.log(json)
    $(text_area_id).val(json.join("\n"))
    $(text_area_id).attr("rows", json.length)
    $(text_area_id).attr("cols", Math.max(...json.map(function (s) {
        return s.length
    })) + 10)
}

function fillInExampleParams(e) {
    verifyRule($("#logic").val())
        .then(function (params) {
            setSampleJson(params, "#verify_json")
        })
        .catch(function (error) {
            console.error(error);
        });
}

function testRuleWithSampleJson(rule_source, test_json) {
    var postData = {
        rule_source: rule_source,
        test_json: test_json
    };

    $.ajax({
        type: 'POST', // HTTP method
        url: `/test_rule`, // URL to which the request will be sent
        data: JSON.stringify(postData),
        contentType: "application/json",
        success: function (response) {
            alert(`Reason: ${response["reason"]}\nRule result: ${response["rule_outcome"]}`)
        },
        error: function (error) {
            // Handle any errors here
            console.error(error);
        }
    });
}