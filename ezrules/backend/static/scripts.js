function get_backtesting_results(rule_id, target_container) {
    $.ajax({
        type: 'GET',
        url: '/get_backtesting_results/' + rule_id,
        success: function (response) {
            let htmlContent = '';
            response.forEach(element => {
                htmlContent += `
                    <li class="list-group-item">
                    <button onclick="getTaskResults('${element.task_id}' ,'#div${element.task_id}')" class="btn btn-primary" type="button" data-bs-toggle="collapse" data-bs-target="#resultscollapse${element.task_id}" aria-expanded="false" aria-controls="resultscollapse${element.task_id}">
                        ${element.task_id} - ${element.created_at}
                    </button>
                    <div class="collapse" id="resultscollapse${element.task_id}">
                        <div class="card card-body" id="div${element.task_id}"></div> 
                    </div>             
                    </li>
                `
            });
            $(target_container).html(htmlContent);
        },
        error: function (error) {
            console.error(error);
        }
    })
}


function submitBackTest(new_rule_logic, r_id) {
    var postData = {
        new_rule_logic: new_rule_logic, r_id: r_id
    };

    $.ajax({
        type: 'POST',
        url: '/backtesting',
        data: JSON.stringify(postData),
        contentType: "application/json",
        success: function (response) {
            get_backtesting_results(r_id, '#backtesting_results')
        },
        error: function (error) {
            console.error(error);
        }
    });
}

function getTaskResults(task_id, target_div_id) {
    $.ajax({
        type: 'GET',
        url: '/get_task_status/' + task_id,
        success: function (response) {
            if (response.ready) {
                $(target_div_id).html(response.result);
            } else {
                $(target_div_id).text("Backfill result is not ready");
            }
        },
        error: function (error) {
            console.error(error);
        }
    })
}

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
    $(text_area_id).show();
    let json = ["{"]
    json.push(...params.map(function (s) {
        return `\t"${s}": ,`;
    }))
    json.push("}")
    $(text_area_id).val(json.join("\n"))
    $(text_area_id).attr("rows", json.length)
    $(text_area_id).attr("cols", Math.max(...json.map(function (s) {
        return s.length
    })) + 10)
}

function updateTextareaSize(textareaId) {
    var textarea = $('#' + textareaId);
    var lines = textarea.val().split('\n');
    var maxLineLength = 0;

    for (var i = 0; i < lines.length; i++) {
        if (lines[i].length > maxLineLength) {
            maxLineLength = lines[i].length;
        }
    }

    textarea.attr('rows', lines.length);
    textarea.attr('cols', maxLineLength);
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