@app.route("/")
def index():
    files = [f for f in os.listdir(OUTPUTS_DIR) if f.endswith(".json")]
    news_list = []

    for f in files:
        with open(os.path.join(OUTPUTS_DIR, f), "r", encoding="utf-8") as file:
            data = json.load(file)

            text = data["processed_text"]

            # анализ
            blocks = [b for b in text.split("\n\n") if b.strip()]
            articles_count = len(blocks)
            chars_count = len(text)

            # 🔥 извлекаем заголовки (**...**)
            titles = re.findall(r"\*\*(.*?)\*\*", text)

            news_list.append({
                "id": f,
                "title": data["original_filename"].replace(".docx", ""),
                "date": datetime.fromisoformat(data["processed_at"]).strftime("%d.%m.%Y %H:%M"),
                "language": data.get("language", "unknown"),
                "articles_count": articles_count,
                "chars_count": chars_count,
                "titles": titles[:5]  # ограничим, например, 5
            })

    news_list.sort(key=lambda x: x["date"], reverse=True)

    return render_template("index.html", news=news_list)



        .topics {
            margin-top: 10px;
            display: flex;
            flex-wrap: wrap; /* перенос на новую строку */
            gap: 6px;
        }

        .topic-tag {
            display: inline-block;
            padding: 4px 10px;
            font-size: 12px;
            background-color: #f2f2f2;
            border-radius: 12px;
            color: #333;
            white-space: nowrap;
            transition: all 0.2s ease;
        }

        .topic-tag:hover {
            background-color: #e0e0e0;
            cursor: pointer;
        }
    </style>


            </div>

            <div class="date">{{ item.date }}</div>

            {% if item.titles %}
            <div class="topics">
                {% for t in item.titles %}
                    <span class="topic-tag">{{ t }}</span>
                {% endfor %}
            </div>
            {% endif %}
        </a>
        {% endfor %}

    </div>