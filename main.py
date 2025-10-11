# 仅导入框架必须的3个模块，无任何多余内容
from astrbot.api.event import AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import json
import os
import time
import uuid
from datetime import datetime


@register("aa_settlement", "anchor", "简易AA记账机器人", "2.9.0", "https://github.com/edc8/bot")
class AASettlementPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # 数据存储与路径
        self.aa_bills = {}  # {用户ID: [账单列表]}
        self.settlement_records = {}
        self.bills_path = os.path.join(os.path.dirname(__file__), "aa_bills.json")
        self.records_path = os.path.join(os.path.dirname(__file__), "settlement_records.json")
        self._load_data()

    # 框架默认消息处理（无需装饰器）
    async def on_message(self, event: AstrMessageEvent):
        content = event.get_content().strip()
        if not content.startswith("/aa"):
            return
        # 解析指令
        parts = list(filter(None, content.split(" ")))[1:]
        resp = await self._handle_cmd(event, parts)
        if resp:
            await event.reply(resp)

    # 指令处理
    async def _handle_cmd(self, event, parts):
        if not parts:
            return self._help()
        
        cmd = parts[0]
        args = parts[1:]
        
        # 创建账单
        if cmd not in ["查", "对账", "清账", "帮助"]:
            return await self._create_bill(event, [cmd] + args)
        # 查看账单
        elif cmd == "查":
            return await self._list_bills(event)
        # 对账
        elif cmd == "对账":
            return await self._show_debt(event, args[0] if args else None)
        # 清账
        elif cmd == "清账":
            return await self._clear_bill(event, args[0] if args else None)
        # 帮助
        elif cmd == "帮助":
            return self._help()
        else:
            return f"未知指令：{cmd}\n{self._help()}"

    # ---------------------- 功能实现 ----------------------
    async def _create_bill(self, event, params):
        if len(params) < 2:
            return "格式错误！示例：/aa 陈 100 或 /aa 张三 李四 600 聚餐"
        
        # 解析金额
        amount = None
        idx = -1
        for i in reversed(range(len(params))):
            try:
                amount = float(params[i])
                idx = i
                break
            except:
                continue
        if not amount or amount <=0:
            return "金额错误！请输入正数"
        
        # 提取信息
        people = params[:idx]
        desc = " ".join(params[idx+1:]) if idx+1 < len(params) else "日常消费"
        uid = event.get_sender_id()
        uname = event.get_sender_name() or f"用户{uid[:4]}"
        if uname not in people:
            people.append(uname)
        people = list(set(people))
        per = round(amount/len(people), 2)
        diff = round(amount - per*len(people), 2)
        
        # 生成账单
        bill_id = str(uuid.uuid4())[:6]
        bill = {
            "bill_id": bill_id,
            "payer": {"id": uid, "name": uname},
            "amount": round(amount,2),
            "desc": desc,
            "people": people,
            "per": per,
            "diff": diff,
            "status": "pending",
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "ts": int(time.time()),
            "debts": [{"debtor": p, "creditor": uname, "amount": per} for p in people if p != uname]
        }
        
        # 保存
        self.aa_bills.setdefault(uid, []).append(bill)
        self._save_data()
        return (
            f"✅ 账单创建成功！\n"
            f"ID：{bill_id}\n"
            f"金额：{bill['amount']}元 | 参与人：{', '.join(people)}\n"
            f"每人：{per}元 | 描述：{desc}\n"
            f"操作：/aa 查 | /aa 清账 {bill_id}"
        )

    async def _list_bills(self, event):
        uid = event.get_sender_id()
        bills = self.aa_bills.get(uid, [])
        if not bills:
            return "暂无账单！创建：/aa 陈 100"
        
        bills_sorted = sorted(bills, key=lambda x: x["ts"], reverse=True)[:10]
        pending = len([b for b in bills if b["status"] == "pending"])
        resp = f"📊 账单列表（待清账：{pending}）\n" + "-"*40 + "\n"
        for i, b in enumerate(bills_sorted, 1):
            status = "🔴 待清账" if b["status"] == "pending" else "🟢 已清账"
            resp += (
                f"{i}. ID：{b['bill_id']} | {status}\n"
                f"   金额：{b['amount']}元 | 描述：{b['desc']}\n"
                f"   时间：{b['time']}\n"
                "-"*40 + "\n"
            )
        return resp

    async def _show_debt(self, event, bill_id):
        if not bill_id:
            return "用法：/aa 对账 [账单ID] | 示例：/aa 对账 abc123"
        
        uid = event.get_sender_id()
        for bill in self.aa_bills.get(uid, []):
            if bill["bill_id"] == bill_id:
                resp = f"📊 账单{bill_id}明细\n" + "-"*40 + "\n"
                resp += f"金额：{bill['amount']}元 | 描述：{bill['desc']}\n"
                resp += "债务：\n"
                for debt in bill["debts"]:
                    resp += f"👉 {debt['debtor']} → {debt['creditor']}：{debt['amount']}元\n"
                return resp
        return f"未找到账单{bill_id}！/aa 查"

    async def _clear_bill(self, event, bill_id):
        if not bill_id:
            return "用法：/aa 清账 [账单ID] | 示例：/aa 清账 abc123"
        
        uid = event.get_sender_id()
        uname = event.get_sender_name() or f"用户{uid[:4]}"
        for bill in self.aa_bills.get(uid, []):
            if bill["bill_id"] == bill_id:
                if bill["status"] == "cleared":
                    return f"账单{bill_id}已清账！"
                
                # 更新状态
                bill["status"] = "cleared"
                bill["clear_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                # 记录清账
                self.settlement_records.setdefault(uid, []).append({
                    "bill_id": bill_id,
                    "desc": bill["desc"],
                    "time": bill["clear_time"],
                    "clearer": uname
                })
                self._save_data()
                return f"✅ 账单{bill_id}已标记清账！"
        return f"未找到账单{bill_id}！/aa 查"

    # ---------------------- 辅助 ----------------------
    def _help(self):
        return (
            "📋 AA记账帮助\n"
            "1. 创建：/aa [人] [金额] [描述]\n"
            "   示例：/aa 陈 100 | /aa 张三 李四 600 聚餐\n"
            "2. 查账单：/aa 查\n"
            "3. 对账：/aa 对账 [ID]\n"
            "4. 清账：/aa 清账 [ID]\n"
            "5. 帮助：/aa 帮助"
        )

    def _load_data(self):
        try:
            if os.path.exists(self.bills_path):
                with open(self.bills_path, "r", encoding="utf-8") as f:
                    self.aa_bills = json.load(f)
            if os.path.exists(self.records_path):
                with open(self.records_path, "r", encoding="utf-8") as f:
                    self.settlement_records = json.load(f)
        except Exception as e:
            logger.error(f"加载数据失败：{e}")

    def _save_data(self):
        try:
            with open(self.bills_path, "w", encoding="utf-8") as f:
                json.dump(self.aa_bills, f, ensure_ascii=False, indent=2)
            with open(self.records_path, "w", encoding="utf-8") as f:
                json.dump(self.settlement_records, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存数据失败：{e}")

    async def terminate(self):
        self._save_data()
