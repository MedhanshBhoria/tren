package models.daos

import models.{Feedback, SQLTables}
import play.api.Configuration
import play.api.db.slick.{DatabaseConfigProvider, HasDatabaseConfigProvider}
import play.db.NamedDatabase
import slick.jdbc.JdbcProfile

import javax.inject.{Inject, Singleton}
import scala.concurrent.{ExecutionContext, Future}

@Singleton
class FeedbackDAO @Inject()(@NamedDatabase("ragmeup") protected val dbConfigProvider: DatabaseConfigProvider, sqlTables: SQLTables)
                           (implicit ec: ExecutionContext, config: Configuration) extends HasDatabaseConfigProvider[JdbcProfile] {

  import profile.api._
  import sqlTables._

  def add(feedback: Feedback): Future[Int] = db.run(Feedbacks += feedback)
}
