from flask import render_template, redirect, url_for, abort, flash, request,\
    current_app, make_response
from flask_login import login_required, current_user
from flask_sqlalchemy import get_debug_queries
from . import main
from .forms import EditProfileForm, EditProfileAdminForm, PostForm, CommentForm
from .. import db
from ..models import Permission, Role, User, Post, Comment, Tag, tagPostTable
from ..decorators import admin_required, permission_required

import logging

logging.basicConfig(level=logging.DEBUG,
                format='%(asctime)s %(levelname)s %(filename)s %(lineno)s %(message)s',
                filename='viewtest.log',
                filemode='w')

import os.path
from PIL import Image
import simplejson
import traceback
from werkzeug import secure_filename
from flask import send_from_directory
from .upload_file import uploadfile
from cv2 import VideoCapture, imwrite

ALLOWED_EXTENSIONS = set(['mp4', 'jpg', 'jpeg', 'png', 'gif', 'bmp', 'pdf', 'mp3', 'txt', 'rar', 'zip', '7zip', 'doc', 'docx'])
def allowed_file(filename):
    return '.' in filename and \
        filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def gen_file_name(filename):
    """
    If file was exist already, rename it and return a new name
    """

    i = 1
    while os.path.exists(os.path.join(current_app.config['UPLOAD_FOLDER'], filename)):
        name, extension = os.path.splitext(filename)
        filename = '%s_%s%s' % (name, str(i), extension)
        i += 1

    return filename


def create_thumbnail(image):
    try:
        base_width = 80
        img = Image.open(os.path.join(current_app.config['UPLOAD_FOLDER'], image))
        w_percent = (base_width / float(img.size[0]))
        h_size = int((float(img.size[1]) * float(w_percent)))
        img = img.resize((base_width, h_size), Image.ANTIALIAS)
        img.save(os.path.join(current_app.config['THUMBNAIL_FOLDER'], image))
        return True
    except:
        print(traceback.format_exc())
        return False
        
def create_poster(video):
    try:
        vidcap = VideoCapture(os.path.join(current_app.config['UPLOAD_FOLDER'], video))
        success,image = vidcap.read()
        imwrite(os.path.join(current_app.config['THUMBNAIL_FOLDER'],"%s.jpg" % (video[:video.rindex('.')])), image)
        return True
    except:
        print(traceback.format_exc())
        return False

@main.route("/edit/upload", methods=['GET', 'POST'])
@main.route("/upload", methods=['GET', 'POST'])
@login_required
def upload():
    if request.method == 'POST':
        files = request.files['file']

        if files:
            filename = secure_filename(files.filename)
            filename = gen_file_name(filename)
            mime_type = files.content_type

            if not allowed_file(files.filename):
                result = uploadfile(name=filename, type=mime_type, size=0, not_allowed_msg="File type not allowed")

            else:
                # save file to disk
                uploaded_file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
                files.save(uploaded_file_path)

                # create thumbnail after saving
                if mime_type.startswith('image'):
                    create_thumbnail(filename)
                elif mime_type.startswith('video'):
                    create_poster(filename)
                
                # get file size after saving
                size = os.path.getsize(uploaded_file_path)

                # return json for js call back
                result = uploadfile(name=filename, type=mime_type, size=size)
            
            return simplejson.dumps({"files": [result.get_file()]})

    if request.method == 'GET':
        # get all file in ./data directory
        files = [f for f in os.listdir(current_app.config['UPLOAD_FOLDER']) if os.path.isfile(os.path.join(current_app.config['UPLOAD_FOLDER'],f))]
        
        file_display = []

        for f in files:
            size = os.path.getsize(os.path.join(current_app.config['UPLOAD_FOLDER'], f))
            file_saved = uploadfile(name=f, size=size)
            file_display.append(file_saved.get_file())

        return simplejson.dumps({"files": file_display})

    return redirect(url_for('index'))

@main.route("/edit/delete/<string:filename>", methods=['DELETE'])
@main.route("/delete/<string:filename>", methods=['DELETE'])
@login_required
def delete(filename):
    file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
    file_thumb_path = os.path.join(current_app.config['THUMBNAIL_FOLDER'], filename)

    if os.path.exists(file_path):
        try:
            os.remove(file_path)

            if os.path.exists(file_thumb_path):
                os.remove(file_thumb_path)
            
            return simplejson.dumps({filename: 'True'})
        except:
            return simplejson.dumps({filename: 'False'})


# serve static files
@main.route("/edit/thumbnail/<string:filename>", methods=['GET'])
@main.route("/thumbnail/<string:filename>", methods=['GET'])
@login_required
def get_thumbnail(filename):
    return send_from_directory(current_app.config['THUMBNAIL_FOLDER'], filename=filename)

@main.route("/edit/data/<string:filename>", methods=['GET'])
@main.route("/data/<string:filename>", methods=['GET'])
@login_required
def get_file(filename):
    return send_from_directory(os.path.join(current_app.config['UPLOAD_FOLDER']), filename=filename)
    

            
@main.after_app_request
def after_request(response):
    for query in get_debug_queries():
        if query.duration >= current_app.config['FLASKY_SLOW_DB_QUERY_TIME']:
            current_app.logger.warning(
                'Slow query: %s\nParameters: %s\nDuration: %fs\nContext: %s\n'
                % (query.statement, query.parameters, query.duration,
                   query.context))
    return response


@main.route('/shutdown')
def server_shutdown():
    if not current_app.testing:
        abort(404)
    shutdown = request.environ.get('werkzeug.server.shutdown')
    if not shutdown:
        abort(500)
    shutdown()
    return 'Shutting down...'


@main.route('/')
def index():
    form = PostForm()
    page = request.args.get('page', 1, type=int)
    tagToShow = request.args.get("tag", None, type=int)
    show_followed, show_tagged = False, False
    if current_user.is_authenticated:
        show_followed = bool(request.cookies.get('show_followed', ''))
    if tagToShow != None:
        query = Post.query.join(tagPostTable, tagPostTable.post_id == Post.id)\
                                     .filter(tagPostTable.tag_id == tagToShow)
    elif show_followed:
        query = current_user.followed_posts
    else:
        query = Post.query
    pagination = query.order_by(Post.timestamp.desc()).paginate(
        page, per_page=current_app.config['FLASKY_POSTS_PER_PAGE'],
        error_out=False)
    posts = pagination.items
    recent_posts = Post.query.order_by(Post.timestamp.desc()).limit(10)

    stmt = db.session.query(tagPostTable.tag_id, db.func.count('*').\
            label('tag_count')).group_by(tagPostTable.tag_id).subquery()
    tagsInSidebar = [t for t in db.session.query(Tag, stmt.c.tag_count).\
                                outerjoin(stmt, Tag.id==stmt.c.tag_id).\
                                order_by(db.desc(stmt.c.tag_count)).limit(10) \
                                if t[1]]
    return render_template('index.html', form=form, posts=posts, 
                           recent_posts=recent_posts, tags=tagsInSidebar,
                           show_followed=show_followed, pagination=pagination)


@main.route('/user/<username>')
def user(username):
    user = User.query.filter_by(username=username).first_or_404()
    page = request.args.get('page', 1, type=int)
    pagination = user.posts.order_by(Post.timestamp.desc()).paginate(
        page, per_page=current_app.config['FLASKY_POSTS_PER_PAGE'],
        error_out=False)
    posts = pagination.items
    return render_template('user.html', user=user, posts=posts,
                           pagination=pagination)


@main.route('/edit-profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    form = EditProfileForm()
    if form.validate_on_submit():
        current_user.name = form.name.data
        current_user.location = form.location.data
        current_user.about_me = form.about_me.data
        db.session.add(current_user._get_current_object())
        db.session.commit()
        flash('Your profile has been updated.')
        return redirect(url_for('.user', username=current_user.username))
    form.name.data = current_user.name
    form.location.data = current_user.location
    form.about_me.data = current_user.about_me
    return render_template('edit_profile.html', form=form)


@main.route('/edit-profile/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_profile_admin(id):
    user = User.query.get_or_404(id)
    form = EditProfileAdminForm(user=user)
    if form.validate_on_submit():
        user.email = form.email.data
        user.username = form.username.data
        user.confirmed = form.confirmed.data
        user.role = Role.query.get(form.role.data)
        user.name = form.name.data
        user.location = form.location.data
        user.about_me = form.about_me.data
        db.session.add(user)
        db.session.commit()
        flash('The profile has been updated.')
        return redirect(url_for('.user', username=user.username))
    form.email.data = user.email
    form.username.data = user.username
    form.confirmed.data = user.confirmed
    form.role.data = user.role_id
    form.name.data = user.name
    form.location.data = user.location
    form.about_me.data = user.about_me
    return render_template('edit_profile.html', form=form, user=user)


@main.route('/post/<int:id>', methods=['GET', 'POST'])
def post(id):
    post = Post.query.get_or_404(id)
    form = CommentForm()
    if form.validate_on_submit():
        comment = Comment(body=form.body.data,
                          post=post,
                          author=current_user._get_current_object())
        db.session.add(comment)
        db.session.commit()
        flash('Your comment has been published.')
        return redirect(url_for('.post', id=post.id, page=-1))
    tags = map(lambda x:Tag.query.filter_by(id=x.tag_id).first(), post.tags)
    page = request.args.get('page', 1, type=int)
    if page == -1:
        page = (post.comments.count() - 1) // \
            current_app.config['FLASKY_COMMENTS_PER_PAGE'] + 1
    pagination = post.comments.order_by(Comment.timestamp.asc()).paginate(
        page, per_page=current_app.config['FLASKY_COMMENTS_PER_PAGE'],
        error_out=False)
    comments = pagination.items
    return render_template('post.html', post=post, form=form, tags=tags,
                           comments=comments, pagination=pagination)


@main.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit(id):
    post = Post.query.get_or_404(id)
    if current_user != post.author and \
            not current_user.can(Permission.ADMIN):
        abort(403)
    form = PostForm()
    currentTags = map(lambda x:Tag.query.filter_by(id=x.tag_id).first(), post.tags)
    if form.validate_on_submit():
        post.title = form.title.data
        tagNewList = [str.strip(x) for x in form.tag.data.split(",")]
        for t in tagNewList:
            if len(t) > 0:
                tagToBe = Tag.query.filter_by(name=t).first()
                if tagToBe == None:
                    tagToBe = Tag(name=t,
                               author=current_user._get_current_object())
                    db.session.add(tagToBe)
                if not tagPostTable.query.filter_by(tag_id=tagToBe.id, 
                                                    post_id=post.id).first():
                    tagPost = tagPostTable(tag_id=tagToBe.id, post_id=post.id)
                    db.session.add(tagPost)
        for cT in currentTags:
            if cT.name not in tagNewList:
                db.session.delete(tagPostTable.query.filter_by(tag_id=cT.id,
                                                    post_id=post.id).first())
        post.body = form.body.data
        db.session.add(post)
        db.session.commit()
        flash('The post has been updated.')
        return redirect(url_for('.post', id=post.id))
    form.title.data = post.title
    form.tag.data = ",".join(map(lambda x:x.name, currentTags))
    form.body.data = post.body
    return render_template('edit_post.html', form=form)
    
    
@main.route('/new', methods=['GET', 'POST'])
@login_required
def new():
    if current_user.can(Permission.WRITE):
        form = PostForm()
        if form.validate_on_submit():
            post = Post(title=form.title.data,
                        body=form.body.data,
                        author=current_user._get_current_object())
            tagNewList = map(str.strip, form.tag.data.split(","))
            for t in tagNewList:
                if len(t) > 0:
                    tagToBe = Tag.query.filter_by(name=t).first()
                    if not tagToBe:
                        tagToBe = Tag(name=t,
                                   author=current_user._get_current_object())
                        db.session.add(tagToBe)
                        db.session.commit()
                    tagPost = tagPostTable(tag_id=tagToBe.id, post_id=post.id)
                    db.session.add(tagPost)
            db.session.add(post)
            db.session.commit()
            flash('New post has been published.')
            return redirect(url_for('.post', id=post.id))
        return render_template('edit_post.html', form=form)


@main.route('/delete_post/<int:id>', methods=['GET'])
@login_required
def delete_post(id):
    post = Post.query.get_or_404(id)
    if current_user != post.author and \
            not current_user.can(Permission.ADMIN):
        abort(403)
    post.delete_comment()
    post.delete_tagPostTable()
    db.session.delete(post)
    db.session.commit()
    flash('Your post has been deleted.')
    return redirect(url_for('.index'))
        

@main.route('/follow/<username>')
@login_required
@permission_required(Permission.FOLLOW)
def follow(username):
    user = User.query.filter_by(username=username).first()
    if user is None:
        flash('Invalid user.')
        return redirect(url_for('.index'))
    if current_user.is_following(user):
        flash('You are already following this user.')
        return redirect(url_for('.user', username=username))
    current_user.follow(user)
    db.session.commit()
    flash('You are now following %s.' % username)
    return redirect(url_for('.user', username=username))


@main.route('/unfollow/<username>')
@login_required
@permission_required(Permission.FOLLOW)
def unfollow(username):
    user = User.query.filter_by(username=username).first()
    if user is None:
        flash('Invalid user.')
        return redirect(url_for('.index'))
    if not current_user.is_following(user):
        flash('You are not following this user.')
        return redirect(url_for('.user', username=username))
    current_user.unfollow(user)
    db.session.commit()
    flash('You are not following %s anymore.' % username)
    return redirect(url_for('.user', username=username))


@main.route('/followers/<username>')
def followers(username):
    user = User.query.filter_by(username=username).first()
    if user is None:
        flash('Invalid user.')
        return redirect(url_for('.index'))
    page = request.args.get('page', 1, type=int)
    pagination = user.followers.paginate(
        page, per_page=current_app.config['FLASKY_FOLLOWERS_PER_PAGE'],
        error_out=False)
    follows = [{'user': item.follower, 'timestamp': item.timestamp}
               for item in pagination.items]
    return render_template('followers.html', user=user, title="Followers of",
                           endpoint='.followers', pagination=pagination,
                           follows=follows)


@main.route('/followed_by/<username>')
def followed_by(username):
    user = User.query.filter_by(username=username).first()
    if user is None:
        flash('Invalid user.')
        return redirect(url_for('.index'))
    page = request.args.get('page', 1, type=int)
    pagination = user.followed.paginate(
        page, per_page=current_app.config['FLASKY_FOLLOWERS_PER_PAGE'],
        error_out=False)
    follows = [{'user': item.followed, 'timestamp': item.timestamp}
               for item in pagination.items]
    return render_template('followers.html', user=user, title="Followed by",
                           endpoint='.followed_by', pagination=pagination,
                           follows=follows)


@main.route('/all')
@login_required
def show_all():
    resp = make_response(redirect(url_for('.index')))
    resp.set_cookie('show_followed', '', max_age=30*24*60*60)
    return resp


@main.route('/followed')
@login_required
def show_followed():
    resp = make_response(redirect(url_for('.index')))
    resp.set_cookie('show_followed', '1', max_age=30*24*60*60)
    return resp


@main.route('/moderate')
@login_required
@permission_required(Permission.MODERATE)
def moderate():
    page = request.args.get('page', 1, type=int)
    pagination = Comment.query.order_by(Comment.timestamp.desc()).paginate(
        page, per_page=current_app.config['FLASKY_COMMENTS_PER_PAGE'],
        error_out=False)
    comments = pagination.items
    return render_template('moderate.html', comments=comments,
                           pagination=pagination, page=page)


@main.route('/moderate/enable/<int:id>')
@login_required
@permission_required(Permission.MODERATE)
def moderate_enable(id):
    comment = Comment.query.get_or_404(id)
    comment.disabled = False
    db.session.add(comment)
    db.session.commit()
    return redirect(url_for('.moderate',
                            page=request.args.get('page', 1, type=int)))


@main.route('/moderate/disable/<int:id>')
@login_required
@permission_required(Permission.MODERATE)
def moderate_disable(id):
    comment = Comment.query.get_or_404(id)
    comment.disabled = True
    db.session.add(comment)
    db.session.commit()
    return redirect(url_for('.moderate',
                            page=request.args.get('page', 1, type=int)))
