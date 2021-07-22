from ruqqus.helpers.wrappers import *
from ruqqus.helpers.get import *

from ruqqus.__main__ import app, cache
from ruqqus.classes.submission import Submission

@app.route("/post/", methods=["GET"])
def slash_post():
	return redirect("/")

# this is a test

@app.route("/notifications", methods=["GET"])
@auth_required
def notifications(v):

	if v and v.is_banned and not v.unban_utc: return render_template("seized.html")

	page = int(request.args.get('page', 1))
	all_ = request.args.get('all', False)
	messages = request.args.get('messages', False)
	posts = request.args.get('posts', False)
	if messages:
		if v.admin_level == 6: comments = g.db.query(Comment).filter(or_(Comment.author_id==v.id, Comment.sentto==v.id, Comment.sentto==0)).filter(Comment.parent_submission == None).order_by(Comment.created_utc.desc()).offset(25 * (page - 1)).limit(26).all()
		else: comments = g.db.query(Comment).filter(or_(Comment.author_id==v.id, Comment.sentto==v.id)).filter(Comment.parent_submission == None).order_by(Comment.created_utc.desc()).offset(25 * (page - 1)).limit(26).all()
		next_exists = (len(comments) == 26)
		comments = comments[:25]
	elif posts:
		cids = v.notification_subscriptions(page=page, all_=all_)
		next_exists = (len(cids) == 26)
		cids = cids[:25]
		comments = get_comments(cids, v=v, sort="new", load_parent=True)
	else:
		cids = v.notification_commentlisting(page=page, all_=all_)
		next_exists = (len(cids) == 26)
		cids = cids[:25]
		comments = get_comments(cids, v=v, sort="new", load_parent=True)

	listing = []
	for c in comments:
		c._is_blocked = False
		c._is_blocking = False
		if c.parent_submission:
			while c.parent_comment:
				parent = c.parent_comment
				if c not in parent.replies2:
					parent.replies2 = parent.replies2 + [c]
					parent.replies = parent.replies2
				c = parent
			if c not in listing:
				listing.append(c)
				c.replies = c.replies2
		else:
			if c.parent_comment:
				while c.level > 1:
					c = c.parent_comment

			if c not in listing:
				listing.append(c)

	return render_template("notifications.html",
						   v=v,
						   notifications=listing,
						   next_exists=next_exists,
						   page=page,
						   standalone=True,
						   render_replies=True,
						   is_notification_page=True)

@cache.memoize(timeout=1500)
def frontlist(v=None, sort="hot", page=1,t="all", ids_only=True, filter_words='', **kwargs):

	posts = g.db.query(Submission).options(lazyload('*')).filter_by(is_banned=False,stickied=False,private=False,).filter(Submission.deleted_utc == 0)

	if v and v.admin_level == 0:
		blocking = g.db.query(
			UserBlock.target_id).filter_by(
			user_id=v.id).subquery()
		blocked = g.db.query(
			UserBlock.user_id).filter_by(
			target_id=v.id).subquery()
		posts = posts.filter(
			Submission.author_id.notin_(blocking),
			Submission.author_id.notin_(blocked)
		)

	if not (v and v.changelogsub):
		posts=posts.join(Submission.submission_aux)
		posts=posts.filter(not_(SubmissionAux.title.ilike(f'%[changelog]%')))

	if v and filter_words:
		for word in filter_words:
			posts=posts.filter(not_(SubmissionAux.title.ilike(f'%{word}%')))

	if t != 'all':
		cutoff = 0
		now = int(time.time())
		if t == 'hour':
			cutoff = now - 3600
		elif t == 'day':
			cutoff = now - 86400
		elif t == 'week':
			cutoff = now - 604800
		elif t == 'month':
			cutoff = now - 2592000
		elif t == 'year':
			cutoff = now - 31536000
		posts = posts.filter(Submission.created_utc >= cutoff)

	gt = kwargs.get("gt")
	lt = kwargs.get("lt")

	if gt:
		posts = posts.filter(Submission.created_utc > gt)

	if lt:
		posts = posts.filter(Submission.created_utc < lt)

	if sort == "hot":
		posts = sorted(posts.all(), key=lambda x: x.hotscore, reverse=True)
	elif sort == "new":
		posts = posts.order_by(Submission.created_utc.desc()).all()
	elif sort == "old":
		posts = posts.order_by(Submission.created_utc.asc()).all()
	elif sort == "controversial":
		posts = sorted(posts.all(), key=lambda x: x.score_disputed, reverse=True)
	elif sort == "top":
		posts = posts.order_by(Submission.score.desc()).all()
	elif sort == "bottom":
		posts = posts.order_by(Submission.score.asc()).all()
	elif sort == "comments":
		posts = posts.order_by(Submission.comment_count.desc()).all()
	elif sort == "random":
		posts = posts.all()
		posts = random.sample(posts, k=len(posts))
	else:
		abort(400)

	firstrange = 25 * (page - 1)
	secondrange = firstrange+1000
	posts = posts[firstrange:secondrange]

	if v and v.hidevotedon: posts = [x for x in posts if x.voted == 0]

	if page == 1: posts = g.db.query(Submission).filter_by(stickied=True).all() + posts

	words = [' captainmeta4 ', ' cm4 ', ' dissident001 ', ' ladine ']

	for post in posts:
		if post.author and post.author.admin_level == 0:
			for word in words:
				if word in post.title.lower():
					posts.remove(post)
					break

	if random.random() < 0.02:
		for post in posts:
			if post.author and post.author.shadowbanned:
				rand = random.randint(500,1400)
				vote = Vote(user_id=rand,
					vote_type=random.choice([-1, 1]),
					submission_id=post.id)
				g.db.add(vote)
				try: g.db.flush()
				except: g.db.rollback()
				post.upvotes = post.ups
				post.downvotes = post.downs
				post.views = post.views + random.randint(7,10)
				g.db.add(post)

	posts = [x for x in posts if not (x.author and x.author.shadowbanned) or (v and v.id == x.author_id)][:26]

	if ids_only:
		posts = [x.id for x in posts]
		return posts
	return posts

@app.route("/", methods=["GET"])
@app.route("/api/v1/listing", methods=["GET"])
@auth_desired
def front_all(v):
	if v and v.is_banned and not v.unban_utc: return render_template("seized.html")

	page = int(request.args.get("page") or 1)

	# prevent invalid paging
	page = max(page, 1)

	if v:
		defaultsorting = v.defaultsorting
		defaulttime = "day"
	else:
		defaultsorting = "hot"
		defaulttime = "day"

	sort=request.args.get("sort", defaultsorting)
	t=request.args.get('t', defaulttime)

	ids = frontlist(sort=sort,
					page=page,
					t=t,
					v=v,
					gt=int(request.args.get("utc_greater_than", 0)),
					lt=int(request.args.get("utc_less_than", 0)),
					filter_words=v.filter_words if v else [],
					)

	# check existence of next page
	next_exists = (len(ids) == 26)
	ids = ids[0:25]

	# check if ids exist
	posts = get_posts(ids, sort=sort, v=v)

	if request.path == "/": return render_template("home.html", v=v, listing=posts, next_exists=next_exists, sort=sort, t=t, page=page)
	else: return jsonify({"data": [x.json for x in posts], "next_exists": next_exists})

@cache.memoize(timeout=1500)
def changeloglist(v=None, sort="new", page=1 ,t="all", **kwargs):

	posts = g.db.query(Submission).options(lazyload('*')).filter_by(is_banned=False,stickied=False,private=False,).filter(Submission.deleted_utc == 0)

	if v and v.admin_level == 0:
		blocking = g.db.query(
			UserBlock.target_id).filter_by(
			user_id=v.id).subquery()
		blocked = g.db.query(
			UserBlock.user_id).filter_by(
			target_id=v.id).subquery()
		posts = posts.filter(
			Submission.author_id.notin_(blocking),
			Submission.author_id.notin_(blocked)
		)

	posts=posts.join(Submission.submission_aux).join(Submission.author)
	posts=posts.filter(SubmissionAux.title.ilike(f'%[changelog]%', User.admin_level == 6))

	if t != 'all':
		cutoff = 0
		now = int(time.time())
		if t == 'hour':
			cutoff = now - 3600
		elif t == 'day':
			cutoff = now - 86400
		elif t == 'week':
			cutoff = now - 604800
		elif t == 'month':
			cutoff = now - 2592000
		elif t == 'year':
			cutoff = now - 31536000
		posts = posts.filter(Submission.created_utc >= cutoff)

	gt = kwargs.get("gt")
	lt = kwargs.get("lt")

	if gt:
		posts = posts.filter(Submission.created_utc > gt)

	if lt:
		posts = posts.filter(Submission.created_utc < lt)

	if sort == "hot":
		posts = sorted(posts.all(), key=lambda x: x.hotscore, reverse=True)
	elif sort == "new":
		posts = posts.order_by(Submission.created_utc.desc()).all()
	elif sort == "old":
		posts = posts.order_by(Submission.created_utc.asc()).all()
	elif sort == "controversial":
		posts = sorted(posts.all(), key=lambda x: x.score_disputed, reverse=True)
	elif sort == "top":
		posts = posts.order_by(Submission.score.desc()).all()
	elif sort == "bottom":
		posts = posts.order_by(Submission.score.asc()).all()
	elif sort == "comments":
		posts = posts.order_by(Submission.comment_count.desc()).all()
	elif sort == "random":
		posts = posts.all()
		posts = random.sample(posts, k=len(posts))
	else:
		abort(400)

	firstrange = 25 * (page - 1)
	secondrange = firstrange+26
	posts = posts[firstrange:secondrange]

	posts = [x.id for x in posts]
	return posts

@app.route("/changelog", methods=["GET"])
@app.route("/api/v1/changelog", methods=["GET"])
@auth_desired
@api("read")
def changelog(v):
	if v and v.is_banned and not v.unban_utc: return render_template("seized.html")

	page = int(request.args.get("page") or 1)
	page = max(page, 1)

	sort=request.args.get("sort", "new")
	t=request.args.get('t', "all")

	ids = changeloglist(sort=sort,
					page=page,
					t=t,
					v=v,
					gt=int(request.args.get("utc_greater_than", 0)),
					lt=int(request.args.get("utc_less_than", 0)),
					)

	# check existence of next page
	next_exists = (len(ids) == 26)
	ids = ids[0:25]

	# check if ids exist
	posts = get_posts(ids, sort=sort, v=v)

	return {'html': lambda: render_template("changelog.html",
											v=v,
											listing=posts,
											next_exists=next_exists,
											sort=sort,
											t=t,
											page=page,
											),
			'api': lambda: jsonify({"data": [x.json for x in posts],
									"next_exists": next_exists
									}
								   )
			}

@app.route("/random", methods=["GET"])
@auth_desired
def random_post(v):
	if v and v.is_banned and not v.unban_utc: return render_template("seized.html")

	x = g.db.query(Submission).filter(Submission.deleted_utc == 0, Submission.is_banned == False, Submission.score > 20)

	total = x.count()
	n = random.randint(0, total - 1)

	post = x.order_by(Submission.id.asc()).offset(n).limit(1).first()
	return redirect(post.permalink)

@cache.memoize(600)
def comment_idlist(page=1, v=None, nsfw=False, sort="new", t="all", **kwargs):

	posts = g.db.query(Submission).options(lazyload('*'))

	posts = posts.subquery()

	comments = g.db.query(Comment).options(lazyload('*'))

	if v and v.admin_level <= 3:
		blocking = g.db.query(
			UserBlock.target_id).filter_by(
			user_id=v.id).subquery()
		blocked = g.db.query(
			UserBlock.user_id).filter_by(
			target_id=v.id).subquery()

		comments = comments.filter(
			Comment.author_id.notin_(blocking),
			Comment.author_id.notin_(blocked)
		)

	if not v or not v.admin_level >= 3:
		comments = comments.filter_by(is_banned=False).filter(Comment.deleted_utc == 0)

	comments = comments.join(posts, Comment.parent_submission == posts.c.id)

	now = int(time.time())
	if t == 'hour':
		cutoff = now - 3600
	elif t == 'day':
		cutoff = now - 86400
	elif t == 'week':
		cutoff = now - 604800
	elif t == 'month':
		cutoff = now - 2592000
	elif t == 'year':
		cutoff = now - 31536000
	else:
		cutoff = 0
	comments = comments.filter(Comment.created_utc >= cutoff)

	if sort == "new":
		comments = comments.order_by(Comment.created_utc.desc()).all()
	elif sort == "old":
		comments = comments.order_by(Comment.created_utc.asc()).all()
	elif sort == "controversial":
		comments = sorted(comments.all(), key=lambda x: x.score_disputed, reverse=True)
	elif sort == "top":
		comments = comments.order_by(Comment.score.desc()).all()
	elif sort == "bottom":
		comments = comments.order_by(Comment.score.asc()).all()

	firstrange = 25 * (page - 1)
	secondrange = firstrange+100
	comments = comments[firstrange:secondrange]

	comments = [x.id for x in comments if not (x.author and x.author.shadowbanned) or (v and v.id == x.author_id)]

	return comments[:26]

@app.route("/comments", methods=["GET"])
@app.route("/api/v1/front/comments", methods=["GET"])
@auth_desired
@api("read")
def all_comments(v):
	if v and v.is_banned and not v.unban_utc: return render_template("seized.html")

	page = int(request.args.get("page", 1))

	sort=request.args.get("sort", "new")
	t=request.args.get("t", "day")

	idlist = comment_idlist(v=v,
							page=page,
							sort=sort,
							t=t,
							)

	comments = get_comments(idlist, v=v)

	next_exists = len(idlist) == 26

	idlist = idlist[0:25]

	board = get_board(1)
	return {"html": lambda: render_template("home_comments.html",
											v=v,
											sort=sort,
											t=t,
											page=page,
											comments=comments,
											standalone=True,
											next_exists=next_exists),
			"api": lambda: jsonify({"data": [x.json for x in comments]})}
